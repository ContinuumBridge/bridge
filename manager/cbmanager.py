#!/usr/bin/env python
# cbanager.py
# Copyright (C) ContinuumBridge Limited, 2013-14 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
START_DELAY = 2.0                  # Delay between starting each adaptor or app
CONDUIT_WATCHDOG_MAXTIME = 600     # Max time with no message before reboot
CONDUIT_MAX_DISCONNECT_COUNT = 600 # Max number of messages before reboot
ELEMENT_WATCHDOG_INTERVAL = 120    # Interval at which to check apps/adaptors have communicated
ELEMENT_POLL_INTERVAL = 3          # Delay between polling each element
APP_STOP_DELAY = 3                 # Time to allow apps/adaprts to stop before killing them
MIN_DELAY = 1                      # Min time to wait when a delay is needed
ModuleName = "Manager"
id = "manager"

import sys
import time
import os
import logging
import subprocess
import json
import urllib
import pexpect
from twisted.internet import threads
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor, defer
from twisted.internet.task import deferLater
from twisted.internet import task
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ReconnectingClientFactory
from pprint import pprint
from cbcommslib import CbClientProtocol
from cbcommslib import CbClientFactory
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory
from cbconfig import *
from dropbox.client import DropboxClient, DropboxOAuth2Flow, DropboxOAuth2FlowNoRedirect
from dropbox.rest import ErrorResponse, RESTSocketError
from dropbox.datastore import DatastoreError, DatastoreManager, Date, Bytes

CONCENTRATOR_PATH = CB_BRIDGE_ROOT + "/concentrator/concentrator.py"
ZWAVE_PATH = CB_BRIDGE_ROOT + "/manager/z-wave-ctrl.py"

class ManageBridge:

    def __init__(self):
        """ apps and adts data structures are stored in a local file.
        """
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        logging.info("%s CB_NO_CLOUD = %s", ModuleName, CB_NO_CLOUD)
        self.bridge_id = "unconfigured"
        self.bridgeStatus = "ok" # Used to set status for sending to supervisor
        self.timeLastConduitMsg = time.time()  # For watchdog
        self.disconnectedCount = 0  # Used to count "disconnected" messages from conduit
        self.zwaveDiscovered = False
        self.bleDiscovered = False
        self.configured = False
        self.reqSync = False
        self.state = "stopped"
        self.concNoApps = False
        self.firstWatchdog = True
        self.elements = {}
        self.appProcs = []
        self.concConfig = []
        self.cbFactory = {} 
        self.appListen = {}
        self.zwaveDevices = []
        self.elFactory = {}
        self.elListen = {}
        self.elProc = {}

        status = self.readConfig()
        logging.info('%s Read config status: %s', ModuleName, status)
        self.initBridge()

    def states(self, action):
        if action == "clear_error":
            self.state = "running"
        else:
            self.state = action
        logging.info('%s state = %s', ModuleName, self.state)
        self.sendStatusMsg("Bridge state: " + self.state)

    def initBridge(self):
        if CB_NO_CLOUD != "True":
            logging.info('%s Starting conduit', ModuleName)
            exe = "/opt/node/bin/node"
            path = CB_BRIDGE_ROOT + "/nodejs/index.js"
            try:
                self.nodejsProc = subprocess.Popen([exe, path,  CB_CONTROLLER_ADDR, \
                                                    CB_BRIDGE_EMAIL, CB_BRIDGE_PASSWORD])
            except:
                logging.error('%s node failed to start. exe = %s', ModuleName, exe)
        else:
            logging.info('%s Running without Cloud Server', ModuleName)
        # Reset Bluetooth interface
        try:
            subprocess.call(["sudo", "hciconfig", "hci0", "down"])
            subprocess.call(["sudo", "hciconfig", "hci0", "up"])
        except:
            logging.warning("%s %s %s Unable to bring up hci0", ModuleName, self.id, self.friendly_name)

        # Give time for node interface to start
        reactor.callLater(START_DELAY, self.startElements)
        reactor.run()

    def listMgrSocs(self):
        mgrSocs = {}
        for d in self.devices:
            mgrSocs[d["id"]] = d["adaptor"]["mgrSoc"]
        for a in self.apps:
            mgrSocs[a["app"]["id"]] = a["app"]["mgrSoc"]
        return mgrSocs

    def startElements(self):
        if self.configured:
            self.removeSecondarySockets()
        els = [{"id": "conc",
                "socket": "skt-mgr-conc",
                "exe": CONCENTRATOR_PATH
               }]
        if CB_ZWAVE_BRIDGE:
            els.append(
               {"id": "zwave",
                "socket": "skt-mgr-zwave",
                "exe": ZWAVE_PATH
               })
        for el in els:
            s = CB_SOCKET_DIR + el["socket"]
            try:
                os.remove(s)
            except:
                logging.debug('%s Socket was not present: %s', ModuleName, s)
            try:
                self.elFactory[el["id"]] = CbServerFactory(self.processClient)
                self.elListen[el["id"]] = reactor.listenUNIX(s, self.elFactory[el["id"]], backlog=4)
                logging.debug('%s Opened manager socket: %s', ModuleName, s)
            except:
                logging.error('%s Failed to open socket: %s', ModuleName, s)
    
            # Now start the element in a subprocess
            try:
                self.elProc[el["id"]] = subprocess.Popen([el["exe"], s, el["id"]])
                logging.debug('%s Started %s', ModuleName, el["id"])
            except:
                logging.error('%s Failed to start %s', ModuleName, el["id"])
    
        # Initiate comms with supervisor, which started the manager in the first place
        s = CB_SOCKET_DIR + "skt-super-mgr"
        initMsg = {"id": "manager",
                   "msg": "status",
                   "status": "ok"} 
        try:
            self.cbSupervisorFactory = CbClientFactory(self.processSuper, initMsg)
            reactor.connectUNIX(s, self.cbSupervisorFactory, timeout=10)
            logging.info('%s Opened supervisor socket %s', ModuleName, s)
        except:
            logging.error('%s Cannot open supervisor socket %s', ModuleName, s)

    def setRunning(self):
        self.states("running")

    def removeSecondarySockets(self):
        for a in self.apps:
            for appDev in a["device_permissions"]:
                socket = appDev["adtSoc"]
                try:
                    os.remove(socket) 
                    logging.debug('%s Socket %s removed', ModuleName, socket)
                except:
                    logging.debug('%s Socket %s already removed', ModuleName, socket)
        for d in self.devices:
            if d["adaptor"]["protocol"] == "zwave":
                socket = d["adaptor"]["zwave_socket"]
                try:
                    os.remove(socket) 
                except:
                    logging.debug('%s Socket %s already removed', ModuleName, socket)

    def startAll(self):
        self.states("starting")
        # Manager sockets may already exist. If so, delete them
        mgrSocs = self.listMgrSocs()
        for s in mgrSocs:
            try:
                os.remove(mgrSocs[s])
            except:
                pass
        # Clear dictionary so that we can recreate sockets
        self.cbFactory.clear()

        # Open sockets for communicating with all apps and adaptors
        for s in mgrSocs:
            try:
                self.cbFactory[s] = CbServerFactory(self.processClient)
                self.appListen[s] = reactor.listenUNIX(mgrSocs[s], self.cbFactory[s], backlog=4)
                logging.info('%s Opened manager socket %s %s', ModuleName, s, mgrSocs[s])
            except:
                logging.error('%s Manager socket already exists %s %s', ModuleName, s, mgrSocs[s])

        # Start adaptors with 2 secs between them to give time for each to start
        delay = START_DELAY 
        # This ensures that any deleted adaptors/apps are removed from watchdog:
        self.elements = {}
        for d in self.devices:
            id = d["id"]
            self.elements[id] = True
            exe = d["adaptor"]["exe"]
            mgrSoc = d["adaptor"]["mgrSoc"]
            friendlyName = d["friendly_name"]
            reactor.callLater(delay, self.startAdaptor, exe, mgrSoc, id, friendlyName)
            delay += START_DELAY
        # Now start all the apps
        delay += START_DELAY*2
        for a in self.apps:
            id = a["app"]["id"]
            self.elements[id] = True
            exe = a["app"]["exe"]
            mgrSoc = a["app"]["mgrSoc"]
            reactor.callLater(delay, self.startApp, exe, mgrSoc, id)
            delay += START_DELAY
        # Start watchdog to monitor apps and adaptors
        reactor.callLater(delay+ELEMENT_WATCHDOG_INTERVAL, self.elementWatchdog)
        # Monitor Bluetooth LE
        #reactor.callInThread(self.monitorLescan)
        # Give time for everything to start before we consider ourselves running
        reactor.callLater(delay+START_DELAY, self.setRunning)
        logging.info('%s All adaptors and apps set to start', ModuleName)

    def startAdaptor(self, exe, mgrSoc, id, friendlyName):
        try:
            p = subprocess.Popen([id, mgrSoc, id], executable=exe)
            self.appProcs.append(p)
            logging.info('%s Started adaptor %s ID: %s', ModuleName, friendlyName, id)
        except:
            logging.error('%s Adaptor %s failed to start', ModuleName, friendlyName)
            logging.error('%s Params: %s %s %s', ModuleName, exe, id, mgrSoc)

    def startApp(self, exe, mgrSoc, id):
        try:
            p = subprocess.Popen([exe, mgrSoc, id])
            self.appProcs.append(p)
            logging.info('%s App %s started', ModuleName, id)
        except:
            logging.error('%s App %s failed to start. exe: %s, socket: %s', ModuleName, id, exe, mgrSoc)

    def monitorLescan(self):
        """ 
            This method is assumed to be called in a Twisted thread.
            It may taken up to LESCAN_TIMEOUT seconds before the thread realises that it should end,
            so this should be set to a fairly small number, certain less than about 6 seconds.
        """
        logging.debug('%s Starting monitorLescan, state = %s', ModuleName, self.state)
        LESCAN_TIMEOUT = 2
        LESCAN_MAX_LOOPS = 20
        while self.state != "stopping":
            time.sleep(2)
            try:
                lescan = pexpect.spawn("hcitool lescan")
            except:
                logging.warning('%s Could not launch lescan pexpect', ModuleName)
            loop = 0
            while self.state != "stopping" and loop < LESCAN_MAX_LOOPS: 
                index = lescan.expect(['.*', pexpect.TIMEOUT, pexpect.EOF], timeout=LESCAN_TIMEOUT)
                #logging.debug('%s monitorLescan. loop:: %s, index %s', ModuleName, str(loop), str(index))
                if index == 0:
                    a = lescan.after.split()
                    #logging.debug('%s : monitorLescan found: %s', ModuleName, a)
                    # a[0] is normally the BT addr. If things have gone wrong it will be the first word of:
                    # "Set scan parameters, failed: Connection timed out". This is pretty fatal, so just 
                    # exit this thread and let any adaptors that care sort out their error conditions.
                    if a != []:
                        if a[0] == "Set":
                            logging.warning('%s monitorLescan fatal error', ModuleName)
                            lescan.sendcontrol("c")
                            time.sleep(1)
                            lescan.kill(9)
                            return 
                        loop = 0
                else:
                    loop += 1
            lescan.sendcontrol("c")
            time.sleep(1)
            lescan.kill(9)
 
    def bleDiscover(self):
        self.bleDiscoveredData = [] 
        exe = CB_BRIDGE_ROOT + "/manager/discovery.py"
        protocol = "btle"
        output = subprocess.check_output([exe, protocol, str(CB_SIM_LEVEL), CB_CONFIG_DIR])
        logging.info('%s Discovery output: %s', ModuleName, output)
        try:
            discOutput = json.loads(output)
        except:
            logging.error('%s Unable to load output from discovery.py', ModuleName)
            reactor.callFromThread(self.sendStatusMsg, "Error. Unable to load output from discovery.py")
        else:   
            if discOutput["status"] == "discovered":
                if self.configured:
                    for d in discOutput["body"]:
                        addrFound = False
                        if d["protocol"] == "btle":
                            for oldDev in self.devices:
                               if oldDev["adaptor"]["protocol"] == "btle": 
                                   if d["mac_addr"] == oldDev["address"]:
                                       addrFound = True
                        if addrFound == False:
                            self.bleDiscoveredData.append(d)  
                else:
                    for d in discOutput["body"]:
                        self.bleDiscoveredData.append(d)  
            else:
                logging.warning('%s Error in ble discovery', ModuleName)
            logging.info('%s Discovered devices:', ModuleName)
            logging.info('%s %s', ModuleName, self.bleDiscoveredData)
            reactor.callFromThread(self.onBLEDiscovered)
            self.discovered = True
            return
    
    def onZwaveDiscovered(self, msg):
        logging.debug('%s onZwaveDiscovered', ModuleName)
        self.zwaveDiscoveredData = msg["body"]
        self.zwaveDiscovered = True
        if self.bleDiscovered:
            self.gatherDiscovered()

    def onBLEDiscovered(self):
        logging.debug('%s onBLEDiscovered', ModuleName)
        self.bleDiscovered = True
        if (CB_ZWAVE_BRIDGE and self.zwaveDiscovered) or CB_SIM_LEVEL == '1' or not CB_ZWAVE_BRIDGE:
            self.gatherDiscovered()

    def gatherDiscovered(self):
        logging.debug('%s gatherDiscovered', ModuleName)
        self.zwaveDiscovered = False
        self.bleDiscovered = False
        d = {}
        d["type"] = "request"
        d["verb"] = "post"
        d["url"] = "/api/bridge/v1/device_discovery/"
        d["channel"] = "bridge_manager"
        d["body"] = []
        for b in self.bleDiscoveredData:
            d["body"].append(b)
        if CB_ZWAVE_BRIDGE and CB_SIM_LEVEL == '0':
            for b in self.zwaveDiscoveredData:
                d["body"].append(b)
        elif CB_SIM_LEVEL == '1':
            b = {'manufacturer_name': 0, 
                 'protocol': 'zwave', 
                 'mac_addr': '40', 
                 'name': 'Binary Power Switch', 
                 'model_number': 0
                }
            d["body"].append(b)
        msg = {"cmd": "msg",
               "msg": d}
        self.cbSendConcMsg(msg)

    def discover(self):
        if CB_ZWAVE_BRIDGE:
            self.elFactory["zwave"].sendMsg({"cmd": "discover"})
        reactor.callInThread(self.bleDiscover)
        self.sendStatusMsg("Press button on device to be discovered now")

    def readConfig(self):
        if CB_DEV_BRIDGE:
            appRoot = CB_HOME + "/apps_dev/"
            adtRoot = CB_HOME + "/adaptors_dev/"
        else:
            appRoot = CB_HOME + "/apps/"
            adtRoot = CB_HOME + "/adaptors/"
        configFile = CB_CONFIG_DIR + "/bridge.config"
        configRead = False
        try:
            with open(configFile, 'r') as configFile:
                config = json.load(configFile)
                configRead = True
                logging.info('%s Read config', ModuleName)
        except:
            logging.warning('%s No config file exists or file is corrupt', ModuleName)
            success= False
        if configRead:
            try:
                self.bridge_id = "BID" + str(config["body"]["id"])
                self.apps = config["body"]["apps"]
                self.devices = config["body"]["devices"]
                success = True
            except:
                success = False
                logging.error('%s bridge.config appears to be corrupt. Ignoring', ModuleName)
            #print "Devices"
            #print "*****************************************************************************"
            #pprint(self.devices)

        if success:
            # Process config to determine routing:
            logging.info('%s Config file for bridge %s read successfully. Processing', ModuleName, self.bridge_id)
            for d in self.devices:
                d["id"] = "DID" + str(d["id"])
                socket = CB_SOCKET_DIR + "SKT-MGR-" + str(d["id"])
                d["adaptor"]["mgrSoc"] = socket
                url = d["adaptor"]["url"]
                split_url = url.split('/')
                if CB_DEV_BRIDGE:
                    dirName = split_url[-3]
                else:
                    dirName = (split_url[-3] + '-' + split_url[-1])[:-7]
                d["adaptor"]["exe"] = adtRoot + dirName + "/" + d["adaptor"]["exe"]
                logging.debug('%s exe: %s', ModuleName, d["adaptor"]["exe"])
                logging.debug('%s protocol: %s', ModuleName, d["device"]["protocol"])
                if d["device"]["protocol"] == "zwave":
                    d["adaptor"]["zwave_socket"] =  CB_SOCKET_DIR + "skt-" + d["id"] + "-zwave"
                # Add a apps list to each device adaptor
                d["adaptor"]["apps"] = []
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["app"]["id"] = "AID" + str(a["app"]["id"])
                url = a["app"]["url"]
                split_url = url.split('/')
                if CB_DEV_BRIDGE:
                    dirName = split_url[-3]
                else:
                    dirName = (split_url[-3] + '-' + split_url[-1])[:-7]
                a["app"]["exe"] = appRoot + dirName + "/" + a["app"]["exe"]
                logging.debug('%s exe: %s', ModuleName, a["app"]["exe"])
                a["app"]["mgrSoc"] = CB_SOCKET_DIR + "SKT-MGR-" + str(a["app"]["id"])
                a["app"]["concSoc"] = CB_SOCKET_DIR + "SKT-CONC-" + str(a["app"]["id"])
                for appDev in a["device_permissions"]:
                    uri = appDev["device_install"]
                    for d in self.devices: 
                        if d["resource_uri"] == uri:
                            socket = CB_SOCKET_DIR + "skt-" \
                                + str(d["id"]) + "-" + str(a["app"]["id"])
                            d["adaptor"]["apps"].append(
                                                    {"adtSoc": socket,
                                                     "name": a["app"]["name"],
                                                     "id": a["app"]["id"]
                                                    }) 
                            appDev["adtSoc"] = socket
                            appDev["id"] = d["id"]
                            appDev["name"] = d["adaptor"]["name"]
                            appDev["friendly_name"] = \
                                d["friendly_name"]
                            appDev["adtSoc"] = socket
                            break
        if success:
            #logging.info('%s Config information processed', ModuleName)
            #logging.info('%s Apps:', ModuleName)
            #logging.info('%s %s', ModuleName, str(self.apps))
            #logging.info('%s', ModuleName)
            #logging.info('%s Devices:', ModuleName)
            #logging.info('%s %s', ModuleName, str(self.devices))
            #logging.info('%s', ModuleName)
            self.configured = True
        return success

    def downloadElement(self, el):
        tarDir = CB_HOME + "/" + el["type"]
        tarFile =  tarDir + "/" + el["name"] + ".tar.gz"
        logging.debug('%s tarDir: %s, tarFile: %s', ModuleName, tarDir, tarFile)
        urllib.urlretrieve(el["url"], tarFile)
        try:
            # By default tar xf overwrites existing files
            subprocess.check_call(["tar", "xfz",  tarFile, "--overwrite", "-C", tarDir, "--transform", "s/-/-v/"])
            logging.info('%s Extracted %s', ModuleName, tarFile)
            return "ok"
        except:
            logging.warning('%s Error extracting %s', ModuleName, tarFile)
            return "Error extraxting " + tarFile 

    def getVersion(self, elementDir):
        try:
            versionFile =  CB_HOME + elementDir + "/version"
            logging.debug('%s versionFile: %s', ModuleName, versionFile)
            with open(versionFile, 'r') as f:
                v = f.read()
            if v.endswith('\n'):
                v = v[:-1]
            return v
        except:
            logging.error('%s No version file for %s', ModuleName, elementDir)
            return "error"

    def updateElements(self):
        """
        Directoriies: CB_HOME/apps/<appname>, CB_HOME/adaptors/<adaptorname>.
        Check if appname/adaptorname exist. If not, download app/adaptor.
        If directory does exist, check version file inside & download if changed.
        """
        updateList = []
        d = CB_HOME + "/adaptors"
        if not os.path.exists(d):
            os.makedirs(d)
        dirs = os.listdir(d)
        for dev in self.devices:
            url = dev["adaptor"]["url"] 
            split_url = url.split('/')
            logging.debug('%s updateElements. split_url: %s', ModuleName, split_url)
            logging.debug('%s updateElements. split_url[-3]: %s', ModuleName, split_url[-3])
            name = (split_url[-3] + '-' + split_url[-1])[:-7]
            logging.debug('%s updateElements. name: %s', ModuleName, name)
            logging.debug('%s updateElements. Current updateList: %s', ModuleName, updateList)
            update = False
            if name not in dirs:
                update = True
                for u in updateList:
                    logging.debug('%s updateElements. u["name"]: %s', ModuleName, u["name"])
                    if u["name"] == name: 
                        update = False
            if update:
                updateList.append({"url": url, "type": "adaptors", "name": name})
        d = CB_HOME + "/apps"
        if not os.path.exists(d):
            os.makedirs(d)
        dirs = os.listdir(d)
        for app in self.apps:
            url = app["app"]["url"]
            split_url = url.split('/')
            logging.debug('%s updateElements. split_url: %s', ModuleName, split_url)
            logging.debug('%s updateElements. split_url[-3]: %s', ModuleName, split_url[-3])
            name = (split_url[-3] + '-' + split_url[-1])[:-7]
            logging.debug('%s updateElements. name: %s', ModuleName, name)
            update = False
            if name not in dirs:
                update = True
                for u in updateList:
                    if u["name"] == name: 
                        update = False
            if update:
                updateList.append({"url": url, "type": "apps", "name": name})

        logging.info('%s updateList: %s', ModuleName, updateList)
        for e in updateList:
            status = self.downloadElement(e)
            if status != "ok":
                self.sendStatusMsg(status)
        if updateList == []:
            return "Updated. All apps and adaptors already at latest versions"
        else:
            feedback = "Updated: "
            for a in updateList:
                feedback += " " + a["name"]
            return feedback

    def updateConfig(self, msg):
        logging.info('%s Config update received from controller:', ModuleName)
        logging.debug('%s %s', ModuleName, str(msg))
        configFile = CB_CONFIG_DIR + "/bridge.config"
        with open(configFile, 'w') as configFile:
            json.dump(msg, configFile)
        success = self.readConfig()
        logging.info('%s Update config, read config status: %s', ModuleName, success)
        if success:
            try:
                status = self.updateElements()
            except:
                logging.info('%s Update config. Something went badly wrong updating apps and adaptors', ModuleName)
                status = "Something went badly wrong updating apps and adaptors"
        else:
            status = "Update failed"
            logging.warning('%s Update config. Failed to update ', ModuleName)
        self.sendStatusMsg(status)

    def upgradeBridge(self):
        upgradeStat = ""
        okToReboot = False
        access_token = os.getenv('CB_DROPBOX_TOKEN', 'NO_TOKEN')
        try:
            logging.info('%s Dropbox access token = %s', ModuleName, access_token)
            self.client = DropboxClient(access_token)
            f, metadata = self.client.get_file_and_metadata('/bridge_clone.tgz')
        except:
            logging.error('%s Cannot access Dropbox to upgrade', ModuleName)
            upgradeStat = "Cannot access Dropbox to upgrade"
        else:
            tarFile = CB_HOME + "/bridge_clone.tgz"
            out = open(tarFile, 'wb')
            out.write(f.read())
            out.close()
            subprocess.call(["tar", "xfz", tarFile])
            logging.info('%s Extracted upgrade tar', ModuleName)

            bridgeDir = CB_HOME + "/bridge"
            bridgeSave = CB_HOME + "/bridge_save"
            bridgeClone = "bridge_clone"
            logging.info('%s Files: %s %s %s', ModuleName, bridgeDir, bridgeSave, bridgeClone)
            try:
                subprocess.call(["rm", "-rf", bridgeSave])
            except:
                logging.warning('%s Could not remove bridgeSave', ModuleName)
                upgradeStat = "OK, but could not delete bridgeSave. Try manual reboot"
            try:
                subprocess.call(["mv", bridgeDir, bridgeSave])
                logging.info('%s Moved bridggeDir to bridgeSave', ModuleName)
                subprocess.call(["mv", bridgeClone, bridgeDir])
                logging.info('%s Moved bridgeClone to bridgeDir', ModuleName)
                upgradeStat = "Upgrade success. Rebooting"
                okToReboot = True
            except:
                upgradeStat = "Failed. Problems moving directories"
        self.sendStatusMsg(upgradeStat)
        if okToReboot:
            self.cbSendSuperMsg({"msg": "reboot"})

    def uploadLog(self, logFile, dropboxPlace, status):
        try:
            f = open(logFile, 'rb')
        except:
            status = "Could not open log file for upload: " + logFile
        else:
            try:
                response = self.client.put_file(dropboxPlace, f)
                #logging.debug('%s Dropbox log upload response: %s', ModuleName, response)
            except:
                status = "Could not upload log file: " + logFile
        reactor.callFromThread(self.sendStatusMsg, status)

    def sendLog(self, logFile):
        status = "Logfile upload failed"
        access_token = os.getenv('CB_DROPBOX_TOKEN', 'NO_TOKEN')
        logging.info('%s Dropbox access token %s', ModuleName, access_token)
        try:
            self.client = DropboxClient(access_token)
            status = "Logfile upload OK" 
        except:
            logging.error('%s Dropbox access token did not work %s', ModuleName, access_token)
            status = "Dropbox access token did not work"
        else:
            hostname = "unknown"
            with open('/etc/hostname', 'r') as hostFile:
                hostname = hostFile.read()
            if hostname.endswith('\n'):
                hostname = hostname[:-1]
            dropboxPlace = '/' + hostname +'.log'
            logging.info('%s Uploading %s to %s', ModuleName, logFile, dropboxPlace)
            status = reactor.callInThread(self.uploadLog, logFile, dropboxPlace, status)
        self.sendStatusMsg(status)

    def doCall(self, cmd):
        try:
            output = subprocess.check_output(cmd, shell=True)
            logging.debug('%s Output from call: %s', ModuleName, output)
        except:
            logging.warning('%s Error in running call: %s', ModuleName, cmd)
            output = "Error in running call"
        reactor.callFromThread(self.sendStatusMsg, output)

    def processSuper(self, msg):
        """  watchdog. Replies with status=ok or a restart/reboot command. """
        if msg["msg"] == "stopall":
            resp = {"msg": "status",
                    "status": "stopping"
                   }
            self.cbSendSuperMsg(resp)
            self.stopApps()
            reactor.callLater(APP_STOP_DELAY, self.killAppProcs)
            reactor.callLater(APP_STOP_DELAY + MIN_DELAY, self.stopAll)
        else:
            if time.time() - self.timeLastConduitMsg > CONDUIT_WATCHDOG_MAXTIME and not CB_NO_CLOUD: 
                logging.info('%s Not heard from conduit for %s. Notifyinng supervisor', ModuleName, CONDUIT_WATCHDOG_MAXTIME)
                resp = {"msg": "status",
                        "status": "disconnected"
                       }
            elif self.disconnectedCount > CONDUIT_MAX_DISCONNECT_COUNT and not CB_NO_CLOUD:
                logging.info('%s Disconnected from bridge controller. Notifying supervisor', ModuleName)
                resp = {"msg": "status",
                        "status": "disconnected"
                       }
            else:
                resp = {"msg": "status",
                        "status": "ok"
                       }
            self.cbSendSuperMsg(resp)

    def processConduitStatus(self, msg):
        self.timeLastConduitMsg = time.time()
        if not "body" in msg:
            logging.warning('%s Unrecognised command received from controller: %s', ModuleName, msg)
            return
        else:
            if msg["body"]["connected"] == True:
                self.disconnectedCount = 0
            else:
                self.disconnectedCount += 1
 
    def processControlMsg(self, msg):
        #logging.info('%s msg received from controller: %s', ModuleName, msg)
        if not "type" in msg: 
            logging.error('%s msg received from controller with no "message" key', ModuleName)
            self.sendStatusMsg("Error. message received from controller with no type key")
            return 
        if msg["type"] == "command":
            if not "body" in msg:
                logging.error('%s command message received from controller with no body', ModuleName)
                self.sendStatusMsg("Error. command message received from controller with no body")
                return 
            if msg["body"] == "start":
                if self.configured:
                    if self.state == "stopped":
                        logging.info('%s Starting adaptors and apps', ModuleName)
                        self.startAll()
                    else:
                        self.sendStatusMsg("Already starting or running. Start command ignored.")
                else:
                    logging.warning('%s Cannot start adaptors and apps. Please run discovery', ModuleName)
                    self.sendStatusMsg("Start command received with no apps and adaptors")
            elif msg["body"] == "discover":
                self.stopApps()
                reactor.callLater(APP_STOP_DELAY, self.killAppProcs)
                reactor.callLater(APP_STOP_DELAY + MIN_DELAY, self.discover)
            elif msg["body"] == "restart":
                logging.info('%s Received restart command', ModuleName)
                self.cbSendSuperMsg({"msg": "restart"})
                self.sendStatusMsg("restarting")
            elif msg["body"] == "reboot":
                logging.info('%s Received reboot command', ModuleName)
                self.cbSendSuperMsg({"msg": "reboot"})
                self.sendStatusMsg("Preparing to reboot")
            elif msg["body"] == "stop":
                if self.state != "stopping" and self.state != "stopped":
                    self.stopApps()
                    reactor.callLater(APP_STOP_DELAY, self.killAppProcs)
                else:
                    self.sendStatusMsg("Already stopped or stopping. Stop command ignored.")
            elif msg["body"] == "upgrade":
                self.stopApps()
                reactor.callLater(APP_STOP_DELAY, self.killAppProcs)
                reactor.callLater(APP_STOP_DELAY + MIN_DELAY, self.upgradeBridge)
            elif msg["body"] == "sendlog" or msg["body"] == "send_log":
                self.sendLog(CB_CONFIG_DIR + '/bridge.log')
            elif msg["body"].startswith("call"):
                # Need to call in thread is case it hangs
                reactor.callInThread(self.doCall, msg["body"][5:])
            elif msg["body"].startswith("upload"):
                # Need to call in thread is case it hangs
                reactor.callInThread(self.sendLog, msg["body"][7:])
            elif msg["body"] == "update_config" or msg["body"] == "update":
                req = {"cmd": "msg",
                       "msg": {"type": "request",
                               "channel": "bridge_manager",
                               "request": "get",
                               "url": "/api/bridge/v1/current_bridge/bridge"}
                      }
                self.cbSendConcMsg(req)
            else:
                logging.warning('%s Unrecognised message received from server: %s', ModuleName, msg)
                self.sendStatusMsg("Unrecognised command received from controller")
        elif msg["type"] == "response":
            self.updateConfig(msg)
            # Need to give concentrator new config if initial one was without apps
            if self.concNoApps:
                req = {"status": "req-config",
                       "type": "conc"}
                self.processClient(req)
                self.concNoApps = False
        elif msg["type"] == "status":
            if not "source" in msg:
                logging.warning('%s Unrecognised command received from controller: %s', ModuleName, msg)
                return
            else:
                self.processConduitStatus(msg)
        else:
            logging.info('%s Unrecognised message received from server: %s', ModuleName, msg)
            self.sendStatusMsg("Unrecognised message received from controller")
 
    def stopApps(self):
        """ Asks apps & adaptors to clean up nicely and die. """
        if self.state != "stopped" and self.state != "stopping":
            self.states("stopping")
            logging.info('%s Stopping apps and adaptors', ModuleName)
            mgrSocs = self.listMgrSocs()
            for a in mgrSocs:
                try:
                    self.cbSendMsg({"cmd": "stop"}, a)
                    logging.info('%s Stopping %s', ModuleName, a)
                except:
                    logging.info('%s Could not send stop message to  %s', ModuleName, a)
        self.cbSendSuperMsg({"msg": "end of stopApps"})

    def killAppProcs(self):
        # Stop listing on sockets
        mgrSocs = self.listMgrSocs()
        for a in mgrSocs:
           logging.debug('%s Stop listening on %s', ModuleName, a)
           self.appListen[a].stopListening()
        # In case apps & adaptors have not shut down, kill their processes.
        for p in self.appProcs:
            try:
                p.kill()
            except:
                logging.debug('%s No process to kill', ModuleName)
        self.removeSecondarySockets()
        # In case some adaptors have not killed gatttool processes:
        subprocess.call(["killall", "gatttool"])
        self.states("stopped")

    def stopAll(self):
        self.sendStatusMsg("Disconnecting. Goodbye, back soon ...")
        logging.info('%s Stopping concentrator', ModuleName)
        if CB_ZWAVE_BRIDGE:
            self.elFactory["zwave"].sendMsg({"cmd": "stop"})
        self.cbSendConcMsg({"cmd": "stop"})
        # Give concentrator a change to stop before killing it and its sockets
        reactor.callLater(MIN_DELAY, self.stopManager)

    def stopManager(self):
        logging.debug('%s stopManager', ModuleName)
        logging.debug('%s stopManager send stopped message to supervisor', ModuleName)
        for el in self.elListen:
            self.elListen[el].stopListening()
        for el in self.elProc:
            try:
                el.kill()
            except:
                logging.debug('%s No element process to kill', ModuleName)
        logging.debug('%s stopManager, killed app processes', ModuleName)
        try:
            self.nodejsProc.kill()
        except:
            logging.debug('%s No node  process to kill', ModuleName)
        logging.debug('%s stopManager, stopped node', ModuleName)
        for soc in self.concConfig:
            socket = soc["appConcSoc"]
            try:
                os.remove(socket) 
                logging.debug('%s Socket %s renoved', ModuleName, socket)
            except:
                logging.debug('%s Socket %s already renoved', ModuleName, socket)
        logging.info('%s Stopping reactor', ModuleName)
        reactor.stop()
        # touch a file so that supervisor can see we have finished
        if not os.path.exists(CB_MANAGER_EXIT):
            open(CB_MANAGER_EXIT, 'w').close()
        sys.exit

    def sendStatusMsg(self, status):
        msg = {"cmd": "msg",
               "msg": {"type": "status",
                       "channel": "bridge_manager",
                       "body": status
                      }
              }
        self.cbSendConcMsg(msg)
 
    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def cbSendConcMsg(self, msg):
        try:
            self.elFactory["conc"].sendMsg(msg)
        except:
            logging.warning('%s Appear to be trying to send a message to concentrator before connected: %s', ModuleName, msg)

    def cbSendSuperMsg(self, msg):
        self.cbSupervisorFactory.sendMsg(msg)

    def elementWatchdog(self):
        """ Checks that all apps and adaptors have communicated within the designated interval. """
        #logging.debug('%s elementWatchdog, elements: %s', ModuleName, str(self.elements))
        if self.state == "running":
            for e in self.elements:
                if self.elements[e] == False:
                    if e != "conc":
                        logging.warning('%s %s has not communicated within watchdog interval', ModuleName, e)
                        self.sendStatusMsg("Watchdog timeout for " + e + " - Restarting")
                        self.cbSendSuperMsg({"msg": "restart"})
                        break
                else:
                    self.elements[e] = False
        reactor.callLater(ELEMENT_WATCHDOG_INTERVAL, self.elementWatchdog)
        if self.firstWatchdog:
            reactor.callLater(ELEMENT_POLL_INTERVAL, self.pollElement)
        else:
            self.firstWatchdog = False

    def pollElement(self):
        for e in self.elements:
            if self.elements[e] == False:
                #logging.debug('%s pollElement, elements: %s', ModuleName, e)
                if e == "conc":
                    self.cbSendConcMsg({"cmd": "status"})
                elif e == "zwave":
                    self.elFactory["zwave"].sendMsg({"cmd": "status"})
                else:
                    self.cbSendMsg({"cmd": "status"}, e)
        reactor.callLater(ELEMENT_POLL_INTERVAL, self.pollElement)

    def processClient(self, msg):
        #logging.debug('%s Received msg; %s', ModuleName, msg)
        # Set watchdog flag
        if not "status" in msg:
            logging.warning('%s No status key in message from client; %s', ModuleName, msg)
            return
        if msg["status"] == "control_msg":
            del msg["status"]
            self.processControlMsg(msg)
            return
        elif not "id" in msg:
            logging.warning('%s No id key in message from client; %s', ModuleName, msg)
            return
        else:
            self.elements[msg["id"]] = True
        if msg["status"] == "req-config":
            if not "type" in msg:
                logging.warning('%s No type key in message from client; %s', ModuleName, msg)
                return
            if msg["type"] == "app":
                for a in self.apps:
                    if a["app"]["id"] == msg["id"]:
                        for c in self.concConfig:
                            if c["id"] == msg["id"]:
                                conc = c["appConcSoc"]
                                response = {"cmd": "config",
                                            "sim": CB_SIM_LEVEL,
                                            "config": {"adaptors": a["device_permissions"],
                                                       "concentrator": conc}}
                                #logging.debug('%s Response: %s %s', ModuleName, msg['id'], response)
                                self.cbSendMsg(response, msg["id"])
                                break
                        break
            elif msg["type"] == "adt": 
                for d in self.devices:
                    if d["id"] == msg["id"]:
                        response = {
                        "cmd": "config",
                        "config": 
                            {"apps": d["adaptor"]["apps"], 
                             "name": d["adaptor"]["name"],
                             "friendly_name": d["friendly_name"],
                             "btAddr": d["address"],
                             "address": d["address"],
                             "btAdpt": "hci0", 
                             "sim": CB_SIM_LEVEL
                            }
                        }
                        if d["device"]["protocol"] == "zwave":
                            response["config"]["zwave_socket"] = d["adaptor"]["zwave_socket"]
                        #logging.debug('%s Response: %s %s', ModuleName, msg['id'], response)
                        self.cbSendMsg(response, msg["id"])
                        break
            elif msg["type"] == "conc":
                if self.configured:
                    for a in self.apps:
                        self.concConfig.append({"id": a["app"]["id"], "appConcSoc": a["app"]["concSoc"]})
                    response = {"cmd": "config",
                                "config": {"bridge_id": self.bridge_id,
                                           "apps": self.concConfig} 
                               }
                else:
                    self.concNoApps = True
                    response = {"cmd": "config",
                                "config": "no_apps"
                               }
                #logging.debug('%s Sending config to conc:  %s', ModuleName, response)
                self.cbSendConcMsg(response)
                # Only start apps & adaptors after concentrator has responded
                if self.configured:
                    reactor.callLater(MIN_DELAY, self.startAll)
            elif msg["type"] == "zwave":
                zwaveConfig = []
                response = {"cmd": "config",
                            "config": "no_zwave"
                           }
                if self.configured:
                    for d in self.devices:
                        if d["device"]["protocol"] == "zwave":
                            zwaveConfig.append({"id": d["id"], 
                                                "socket": d["adaptor"]["zwave_socket"],
                                                "address": d["address"]
                                              })
                            response["config"] = zwaveConfig 
                else:
                    self.noZwave = True
                #logging.debug('%s Sending config to conc:  %s', ModuleName, response)
                self.elFactory["zwave"].sendMsg(response)
            else:
                logging.warning('%s Config req from unknown instance type: %s', ModuleName, msg['id'])
                response = {"cmd": "error"}
                self.cbSendMsg(response, msg["id"])
        elif msg["status"] == "log":
            if "log" in msg:
                log = "log " + msg["id"] + ": " + msg["log"]
            else:
                log = "log " + msg["id"] + ": No log message provided" 
            logging.warning('%s %s', ModuleName, log)
            self.sendStatusMsg(log)
        elif msg["status"] == "discovered":
            if msg["id"] == "zwave":
                self.onZwaveDiscovered(msg)
            else:
                logging.warning('%s Discovered message from unexpected source: %s', ModuleName, msg["id"])
        elif msg["status"] == "state":
            if "state" in msg:
                logging.debug('%s %s %s', ModuleName, msg["id"], msg["state"])
            else:
                logging.warning('%s Received state message from %s with no state', ModuleName, msg["id"])
        elif msg["status"] == "error":
                logging.warning('%s Error status received from %s. Restarting', ModuleName, msg["id"])
                self.sendStatusMsg("Error status received from " + msg["id"] + " - Restarting")
                self.cbSendSuperMsg({"msg": "restart"})
 
if __name__ == '__main__':
    m = ManageBridge()
