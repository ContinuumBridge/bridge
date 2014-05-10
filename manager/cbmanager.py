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

class ManageBridge:

    def __init__(self):
        """ apps and adts data structures are stored in a local file.
        """
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        logging.info("%s CB_NO_CLOUD = %s", ModuleName, CB_NO_CLOUD)
        self.bridgeStatus = "ok" # Used to set status for sending to supervisor
        self.timeLastConduitMsg = time.time()  # For watchdog
        self.disconnectedCount = 0  # Used to count "disconnected" messages from conduit
        self.discovered = False
        self.configured = False
        self.reqSync = False
        self.state = "stopped"
        self.concNoApps = False
        self.elements = {}
        self.appProcs = []
        self.concConfig = []
        self.cbFactory = {} 
        self.appListen = {}
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
        reactor.callLater(START_DELAY, self.startConcentrator)
        if self.configured:
            reactor.callLater(START_DELAY*2, self.startAll)
        reactor.run()

    def listMgrSocs(self):
        mgrSocs = {}
        for d in self.devices:
            mgrSocs[d["id"]] = d["adaptor"]["mgrSoc"]
        for a in self.apps:
            mgrSocs[a["app"]["id"]] = a["app"]["mgrSoc"]
        return mgrSocs

    def startConcentrator(self):
        # Open a socket for communicating with the concentrator
        s = CB_SOCKET_DIR + "skt-mgr-conc"
        try:
            os.remove(s)
        except:
            logging.debug('%s Conc socket was not present: %s', ModuleName, s)
        try:
            self.cbConcFactory = CbServerFactory(self.processClient)
            self.concListen = reactor.listenUNIX(s, self.cbConcFactory, backlog=4)
            logging.debug('%s Opened manager socket: %s', ModuleName, s)
        except:
            logging.error('%s Failed to open manager-conc socket: %s', ModuleName, s)

        # Now start the concentrator in a subprocess
        exe = self.concPath
        id = "conc"
        mgrSoc = CB_SOCKET_DIR + "skt-mgr-conc"
        try:
            self.concProc = subprocess.Popen([exe, mgrSoc, id])
            logging.debug('%s Started concentrator', ModuleName)
        except:
            logging.error('%s Failed to start concentrator', ModuleName)

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
        # Give time for everything to start before we consider ourselves running
        reactor.callLater(delay+START_DELAY, self.setRunning)
        logging.info('%s All adaptors and apps set to start', ModuleName)

    def startAdaptor(self, exe, mgrSoc, id, friendlyName):
        try:
            p = subprocess.Popen([exe, mgrSoc, id])
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

    def doDiscover(self):
        self.discoveredDevices = {}
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
            self.discoveredDevices["type"] = "request"
            self.discoveredDevices["verb"] = "post"
            self.discoveredDevices["url"] = "/api/bridge/v1/device_discovery/"
            self.discoveredDevices["body"] = []
            if self.configured:
                for d in discOutput["body"]:
                    addrFound = False
                    if d["protocol"] == "btle":
                        for oldDev in self.devices:
                           if oldDev["adaptor"]["protocol"] == "btle": 
                               if d["mac_addr"] == oldDev["mac_addr"]:
                                   addrFound = True
                    if addrFound == False:
                        self.discoveredDevices["body"].append(d)  
            else:
                for d in discOutput["body"]:
                    self.discoveredDevices["body"].append(d)  
            logging.info('%s Discovered devices:', ModuleName)
            logging.info('%s %s', ModuleName, self.discoveredDevices)
            msg = {"cmd": "msg",
                   "msg": self.discoveredDevices}
            reactor.callFromThread(self.cbSendConcMsg, msg)
            self.discovered = True
    
    def discover(self):
        # Call in thread so that manager can still process other messages
        reactor.callInThread(self.doDiscover)

    def readConfig(self):
        if CB_DEV_BRIDGE:
            appRoot = CB_HOME + "/apps_dev/"
            adtRoot = CB_HOME + "/adaptors_dev/"
        else:
            appRoot = CB_HOME + "/apps/"
            adtRoot = CB_HOME + "/adaptors/"
        self.concPath = CB_BRIDGE_ROOT + "/concentrator/concentrator.py"
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
                self.apps = config["body"]["apps"]
                self.devices = config["body"]["devices"]
                success = True
            except:
                success = False
                logging.error('%s bridge.config appears to be corrupt. Ignoring', ModuleName)

        if success:
            # Process config to determine routing:
            logging.info('%s Success. Processing config', ModuleName)
            for d in self.devices:
                d["id"] = "dev" + str(d["id"])
                socket = CB_SOCKET_DIR + "skt-mgr-" + str(d["id"])
                d["adaptor"]["mgrSoc"] = socket
                d["adaptor"]["exe"] = adtRoot + d["adaptor"]["url"] + "/" + d["adaptor"]["exe"]
                # Add a apps list to each device adaptor
                d["adaptor"]["apps"] = []
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["app"]["id"] = "app" + str(a["app"]["id"])
                a["app"]["exe"] = appRoot + a["app"]["url"] + "/" + a["app"]["exe"]
                a["app"]["mgrSoc"] = CB_SOCKET_DIR + "skt-mgr-" + str(a["app"]["id"])
                a["app"]["concSoc"] = CB_SOCKET_DIR + "skt-conc-" + str(a["app"]["id"])
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
            logging.info('%s Config information processed', ModuleName)
            logging.info('%s Apps:', ModuleName)
            logging.info('%s %s', ModuleName, str(self.apps))
            logging.info('%s', ModuleName)
            logging.info('%s Devices:', ModuleName)
            logging.info('%s %s', ModuleName, str(self.devices))
            logging.info('%s', ModuleName)
            self.configured = True
        return success

    def downloadElement(self, el):
        access_token = os.getenv('CB_DROPBOX_TOKEN', 'NO_TOKEN')
        try:
            logging.info('%s Dropbox access token = %s', ModuleName, access_token)
            self.client = DropboxClient(access_token)
        except:
            logging.error('%s Cannot access Dropbox to update apps/adaptors', ModuleName)
            return "Cannot access Dropbox to update apps/adaptors"
        try:
            fileName = el["url"] + ".tgz"
            f, metadata = self.client.get_file_and_metadata(fileName)
        except:
            logging.warning('%s Cannot download file %s', ModuleName, fileName)
            return "Cannot download file " + fileName 
        try:
            tarDir = CB_HOME + "/" + el["type"]
            tarFile =  tarDir + "/" + el["url"] + ".tgz"
            logging.debug('%s tarFile = %s', ModuleName, tarFile)
            out = open(tarFile, 'wb')
            out.write(f.read())
            out.close()
        except:
            logging.warning('%s Problem downloading %s', ModuleName, fileName)
            return "Problem downloading " + fileName 
        try:
            # By default tar xf overwrites existing files
            subprocess.check_call(["tar", "xfz",  tarFile, "--overwrite", "-C", tarDir])
            logging.info('%s Extracted %s', ModuleName, tarFile)
            return "ok"
        except:
            logging.warning('%s Error extracting %s', ModuleName, tarFile)
            return "Error extraxting " + fileName 

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
        dirs = os.listdir(CB_HOME + "/adaptors")
        for dev in self.devices:
            url = dev["adaptor"]["url"] 
            if url in dirs:
                v =  self.getVersion("/adaptors/" + url)
                if v != "error":
                    if dev["adaptor"]["version"] != v:
                        updateList.append({"url": url,
                                           "type": "adaptors"})
            else:
                updateList.append({"url": url,
                                   "type": "adaptors"})
        for app in self.apps:
            dirs = os.listdir(CB_HOME + "/apps")
            url = app["app"]["url"]
            if url in dirs:
                v =  self.getVersion("/apps/" + url)
                logging.debug('%s updateElements. old version: %s, new: %s ', ModuleName, v, app["app"]["version"])
                if v != "error":
                    if app["app"]["version"] != v:
                        updateList.append({"url": url,
                                           "type": "apps"})
            else:
                updateList.append({"url": url,
                                   "type": "apps"})

        logging.debug('%s updateList: %s', ModuleName, updateList)
        for e in updateList:
            status = self.downloadElement(e)
            if status != "ok":
                self.sendStatusMsg(status)
        if updateList == []:
            return "Nothing to update"
        else:
            return "Updated"

    def updateConfig(self, msg):
        logging.debug('%s Config received from controller:', ModuleName)
        logging.debug('%s %s', ModuleName, str(msg))
        configFile = CB_CONFIG_DIR + "/bridge.config"
        with open(configFile, 'w') as configFile:
            json.dump(msg, configFile)
        success = self.readConfig()
        logging.info('%s Update config, read config status: %s', ModuleName, success)
        if success:
            status = self.updateElements()
        else:
            status = "Update failed"
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

    def sendLog(self):
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
            logFile = CB_CONFIG_DIR + '/bridge.log'
            logging.info('%s Uploading %s to %s', ModuleName, logFile, dropboxPlace)
            try:
                f = open(logFile, 'rb')
            except:
                status = "Could not open log file for upload: " + logFile
            else:
                try:
                    response = self.client.put_file(dropboxPlace, f)
                    logging.debug('%s Dropbox log upload response: %s', ModuleName, response)
                except:
                    status = "Could not upload log file: " + logFile
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
            if time.time() - self.timeLastConduitMsg > CONDUIT_WATCHDOG_MAXTIME and CB_NO_CLOUD != "True": 
                logging.info('%s Not heard from conduit for %s. Notifyinng supervisor', ModuleName, CONDUIT_WATCHDOG_MAXTIME)
                resp = {"msg": "status",
                        "status": "disconnected"
                       }
            elif self.disconnectedCount > CONDUIT_MAX_DISCONNECT_COUNT and CB_NO_CLOUD != "True":
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
                logging.info('%s Disconnected message received from conduit', ModuleName)
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
                self.sendLog()
            elif msg["body"].startswith("call"):
                # Need to call in thread is case it hangs
                reactor.callInThread(self.doCall, msg["body"][5:])
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
        for a in self.apps:
            for appDev in a["device_permissions"]:
                socket = appDev["adtSoc"]
                try:
                    os.remove(socket) 
                    logging.debug('%s Socket %s removed', ModuleName, socket)
                except:
                    logging.debug('%s Socket %s already removed', ModuleName, socket)
        # In case some adaptors have not killed gatttool processes:
        subprocess.call(["killall", "gatttool"])
        self.states("stopped")

    def stopAll(self):
        self.sendStatusMsg("Disconnecting. Goodbye, back soon ...")
        logging.info('%s Stopping concentrator', ModuleName)
        self.cbSendConcMsg({"cmd": "stop"})
        # Give concentrator a change to stop before killing it and its sockets
        reactor.callLater(MIN_DELAY, self.stopManager)

    def stopManager(self):
        self.concListen.stopListening()
        try:
            self.concProc.kill()
        except:
            logging.debug('%s No concentrator process to kill', ModuleName)
        try:
            self.nodejsProc.kill()
        except:
            logging.debug('%s No node  process to kill', ModuleName)
        for soc in self.concConfig:
            socket = soc["appConcSoc"]
            try:
                os.remove(socket) 
                logging.debug('%s Socket %s renoved', ModuleName, socket)
            except:
                logging.debug('%s Socket %s already renoved', ModuleName, socket)
        self.cbSendSuperMsg({"msg": "stopped"})
        logging.info('%s Stopping reactor', ModuleName)
        reactor.stop()
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
            self.cbConcFactory.sendMsg(msg)
        except:
            logging.warning('%s Appear to be trying to send a message to concentrator before connected', ModuleName)

    def cbSendSuperMsg(self, msg):
        self.cbSupervisorFactory.sendMsg(msg)

    def elementWatchdog(self):
        """ Checks that all apps and adaptors have communicated within the designated interval. """
        if self.state == "running":
            for e in self.elements:
                if self.elements[e]== False:
                    if e != "conc":
                        logging.warning('%s %s has not communicated within watchdog interval', ModuleName, e)
                        self.sendStatusMsg("Watchdog timeout for " + e + " - Restarting")
                        self.cbSendSuperMsg({"msg": "restart"})
                        break
                else:
                    self.elements[e] = False
        reactor.callLater(ELEMENT_WATCHDOG_INTERVAL, self.elementWatchdog)

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
                                logging.debug('%s Response: %s %s', ModuleName, msg['id'], response)
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
                             "btAddr": d["mac_addr"],
                             "btAdpt": "hci0", 
                             "sim": CB_SIM_LEVEL
                            }
                        }
                        logging.debug('%s Response: %s %s', ModuleName, msg['id'], response)
                        self.cbSendMsg(response, msg["id"])
                        break
            elif msg["type"] == "conc":
                self.concConfig = []
                if self.configured:
                    for a in self.apps:
                        self.concConfig.append({"id": a["app"]["id"],
                                           "appConcSoc": a["app"]["concSoc"]})
                    response = {"cmd": "config",
                                "config": self.concConfig 
                               }
                else:
                    self.concNoApps = True
                    response = {"cmd": "config",
                                "config": "no_apps"
                               }
                logging.debug('%s Sending config to conc:  %s', ModuleName, response)
                self.cbSendConcMsg(response)
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
