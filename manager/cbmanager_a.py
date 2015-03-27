#!/usr/bin/env python
# cbanager_a.py
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
from twisted.internet import reactor, defer
from twisted.internet import task
from cbcommslib import CbClientProtocol
from cbcommslib import CbClientFactory
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory
from cbcommslib import isotime
from cbconfig import *
from dropbox.client import DropboxClient, DropboxOAuth2Flow, DropboxOAuth2FlowNoRedirect
from dropbox.rest import ErrorResponse, RESTSocketError
from dropbox.datastore import DatastoreError, DatastoreManager, Date, Bytes
import procname
if CB_SIM_LEVEL == '1':
    from simdiscover import SimDiscover

CB_INC_UPGRADE_URL = 'https://github.com/ContinuumBridge/cbridge/releases/download/Incremental/bridge_clone_inc.tar.gz'
CB_FULL_UPGRADE_URL = 'https://github.com/ContinuumBridge/cbridge/releases/download/Full/bridge_clone.tar.gz'
CB_DEV_UPGRADE_URL = 'https://github.com/ContinuumBridge/cbridge/releases/download/Dev/bridge_clone.tar.gz'
CONCENTRATOR_PATH = CB_BRIDGE_ROOT + "/concentrator/concentrator.py"
ZWAVE_PATH = CB_BRIDGE_ROOT + "/manager/z-wave-ctrl.py"
USB_DEVICES_FILE = CB_BRIDGE_ROOT + "/manager/usb_devices.json"

class ManageBridge:

    def __init__(self):
        """ apps and adts data structures are stored in a local file.
        """
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(levelname)s: %(message)s')
        logging.info("%s CB_NO_CLOUD = %s", ModuleName, CB_NO_CLOUD)
        procname.setprocname('captain')
        self.bridge_id = CB_BID
        logging.info("%s CB_BID = %s", ModuleName, CB_BID)
        self.bridgeStatus = "ok" # Used to set status for sending to supervisor
        self.timeLastConduitMsg = time.time()  # For watchdog
        self.disconnectedCount = 0  # Used to count "disconnected" messages from conduit
        self.controllerConnected = False
        self.zwaveDiscovered = False
        self.bleDiscovered = False
        self.configured = False
        self.restarting = False
        self.reqSync = False
        self.state = "stopped"
        self.concNoApps = False
        self.firstWatchdog = True
        self.elements = {}
        self.appProcs = []
        self.concConfig = []
        self.appConfigured = []
        self.cbFactory = {} 
        self.appListen = {}
        self.zwaveDevices = []
        self.elFactory = {}
        self.elListen = {}
        self.elProc = {}
        self.batteryLevels = []
        self.idToName = {}
        self.bluetooth = False

        status = self.readConfig()
        logging.info('%s Read config status: %s', ModuleName, status)
        if CB_SIM_LEVEL == '1':
            self.simDiscover = SimDiscover(self.bridge_id)
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
            except Exception as ex:
                logging.error('%s node failed to start. exe = %s', ModuleName, exe)
                logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        else:
            logging.info('%s Running without Cloud Server', ModuleName)
        # Give time for node interface to start
        reactor.callLater(START_DELAY + 5, self.startElements)
        reactor.run()

    def checkBluetooth(self):
        lsusb = subprocess.check_output(["lsusb"])
        if "Bluetooth" in lsusb:
            self.bluetooth = True
            self.resetBluetooth
            logging.info("%s Bluetooth dongle detected", ModuleName)
            reactor.callFromThread(self.sendStatusMsg, "Note: Bluetooth is enabled")
        else:
            self.bluetooth = False
            logging.info("%s No Bluetooth dongle detected", ModuleName)
            reactor.callFromThread(self.sendStatusMsg, "Note: No Bluetooth interface found")

    def resetBluetooth(self):
        # Called in a thread
        logging.debug("%s resetBluetooth", ModuleName)
        try:
            s = subprocess.check_output(["hciconfig", "hci0", "down"])
            if s != '':
                logging.warning("%s Problem configuring hci0 (down): %s", ModuleName, s)
            else:
                logging.debug("%s hci0 down OK", ModuleName)
            time.sleep(MIN_DELAY)
            s = subprocess.check_output(["hciconfig", "hci0", "up"])
            if s != '':
                logging.warning("%s Problem configuring hci0 (up), %s", ModuleName, s)
            else:
                logging.debug("%s hci0 up OK", ModuleName)
        except Exception as ex:
            logging.warning("%s Unable to configure hci0", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))

    def listMgrSocs(self):
        mgrSocs = {}
        for d in self.devices:
            mgrSocs[d["id"]] = d["adaptor"]["mgrSoc"]
        for a in self.apps:
            mgrSocs[a["app"]["id"]] = a["app"]["mgrSoc"]
        return mgrSocs

    def startElements(self):
        reactor.callInThread(self.checkBluetooth)
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
                self.elFactory[el["id"]] = CbServerFactory(self.onClientMessage)
                self.elListen[el["id"]] = reactor.listenUNIX(s, self.elFactory[el["id"]], backlog=4)
                logging.debug('%s Opened manager socket: %s', ModuleName, s)
            except Exception as ex:
                logging.error('%s Failed to open socket: %s', ModuleName, s)
                logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
    
            # Now start the element in a subprocess
            try:
                self.elProc[el["id"]] = subprocess.Popen([el["exe"], s, el["id"]])
                logging.debug('%s Started %s', ModuleName, el["id"])
            except Exception as ex:
                logging.error('%s Failed to start %s', ModuleName, el["id"])
                logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
    
        # Initiate comms with supervisor, which started the manager in the first place
        s = CB_SOCKET_DIR + "skt-super-mgr"
        initMsg = {"id": "manager",
                   "msg": "status",
                   "status": "ok"} 
        try:
            self.cbSupervisorFactory = CbClientFactory(self.processSuper, initMsg)
            reactor.connectUNIX(s, self.cbSupervisorFactory, timeout=10)
            logging.info('%s Opened supervisor socket %s', ModuleName, s)
        except Exception as ex:
            logging.error('%s Cannot open supervisor socket %s', ModuleName, s)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))

    def setRunning(self):
        self.states("running")

    def removeSecondarySockets(self):
        # There should be no sockets to remove if there is no config file
        # Also there are no apps and adaptors without a config file
        if self.configured:
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
                self.cbFactory[s] = CbServerFactory(self.onClientMessage)
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
        except Exception as ex:
            logging.error('%s Adaptor %s failed to start', ModuleName, friendlyName)
            logging.error('%s Params: %s %s %s', ModuleName, exe, id, mgrSoc)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))

    def startApp(self, exe, mgrSoc, id):
        try:
            p = subprocess.Popen([exe, mgrSoc, id])
            self.appProcs.append(p)
            logging.info('%s App %s started', ModuleName, id)
        except Exception as ex:
            logging.error('%s App %s failed to start. exe: %s, socket: %s', ModuleName, id, exe, mgrSoc)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))

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
        self.resetBluetooth()
        self.bleDiscoveredData = [] 
        exe = CB_BRIDGE_ROOT + "/manager/discovery.py"
        protocol = "ble"
        output = subprocess.check_output([exe, protocol, str(CB_SIM_LEVEL), CB_CONFIG_DIR])
        logging.info('%s Discovery output: %s', ModuleName, output)
        try:
            discOutput = json.loads(output)
        except Exception as ex:
            logging.error('%s Unable to load output from discovery.py', ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            reactor.callFromThread(self.sendStatusMsg, "Error. Unable to load output from discovery.py")
        else:   
            bleNames = ""
            if discOutput["status"] == "discovered":
                if self.configured:
                    for d in discOutput["body"]:
                        addrFound = False
                        if d["protocol"] == "ble":
                            if self.devices == []:
                                bleNames += d["name"] + ", "
                            else:
                                for oldDev in self.devices:
                                    if oldDev["device"]["protocol"] == "btle" or oldDev["device"]["protocol"] == "ble": 
                                        if d["address"] == oldDev["address"]:
                                            addrFound = True
                                        else:
                                            bleNames += d["name"] + ", "
                        if addrFound == False:
                            self.bleDiscoveredData.append(d)  
                else:
                    for d in discOutput["body"]:
                        self.bleDiscoveredData.append(d)  
                        bleNames += d["name"] + ", "
            else:
                logging.warning('%s Error in ble discovery', ModuleName)
            logging.info('%s Discovered devices:', ModuleName)
            logging.info('%s %s', ModuleName, self.bleDiscoveredData)
            if bleNames != "":
                bleNames= bleNames[:-2]
                logging.info('%s  BLE devices found: %s', ModuleName, bleNames)
                reactor.callFromThread(self.sendStatusMsg, "BLE devices found: " + bleNames)
            reactor.callFromThread(self.onBLEDiscovered)
            self.discovered = True
            return
    
    def usbDiscover(self):
        self.usbDiscovered = False
        usb_devices = []    # In case file doesn't load
        self.usbDiscoveredData = []
        try:
            with open(USB_DEVICES_FILE, 'r') as f:
                usb_devices = json.load(f)
                logging.info('%s Read usb devices file', ModuleName)
        except:
            logging.warning('%s No usb devices file exists or file is corrupt', ModuleName)
        lsusb = subprocess.check_output(["lsusb"])
        devs = lsusb.split("\n")
        for d in devs:
            details = d.split()
            logging.debug('%s usbDiscover. details: %s', ModuleName, details)
            if details != []:
                for known_device in usb_devices:
                    if details[5] == known_device["id"]:
                        if self.configured:
                            addrFound = False
                            address = details[3][:3]
                            for oldDev in self.devices:
                                if oldDev["device"]["protocol"] == "zwave":
                                        if address == oldDev["address"]:
                                            addrFound = True
                                            break
                            if addrFound == False:
                                self.usbDiscovered = True
                                self.usbDiscoveredData.append({"protocol": "zwave",
                                                               "name": known_device["name"],
                                                               "mac_addr": address
                                                             })
                                reactor.callFromThread(self.gatherDiscovered)
                        else:
                            self.usbDiscovered = True
                            self.usbDiscoveredData.append({"protocol": "zwave",
                                                           "name": known_device["name"],
                                                           "mac_addr": address
                                                         })
                            reactor.callFromThread(self.gatherDiscovered)
    
    def onZwaveDiscovering(self, msg):
        logging.debug('%s onZwaveDiscovering', ModuleName)
        self.zwaveDiscovering = True
        self.sendStatusMsg("Z-wave device found. Identifyiing it. This may take up to 30 seconds.")

    def onZwaveDiscovered(self, msg):
        logging.debug('%s onZwaveDiscovered', ModuleName)
        self.zwaveDiscoveredData = msg["body"]
        self.zwaveDiscovered = True
        self.gatherDiscovered()

    def onBLEDiscovered(self):
        logging.debug('%s onBLEDiscovered', ModuleName)
        self.bleDiscovered = True
        if not self.zwaveDiscovered or self.zwaveDiscovering:
            self.gatherDiscovered()

    def gatherDiscovered(self):
        logging.debug('%s gatherDiscovered', ModuleName)
        d = {}
        d["source"] = self.bridge_id
        d["destination"] = "cb"
        d["time_sent"] = isotime()
        d["body"] = {}
        d["body"]["resource"] = "/api/bridge/v1/discovered_device/"
        d["body"]["verb"] = "patch"
        d["body"]["body"] = {}
        d["body"]["body"]["objects"] = []
        if self.usbDiscovered:
            d["body"]["body"]["objects"] = self.usbDiscoveredData
        else:
            if self.bleDiscovered and not self.zwaveDiscovered:
                if self.bleDiscoveredData:
                    for b in self.bleDiscoveredData:
                        d["body"]["body"]["objects"].append(b)
                else:
                    self.sendStatusMsg("No Bluetooth devices found.")
            if self.zwaveDiscovered and CB_SIM_LEVEL == '0':
                for b in self.zwaveDiscoveredData:
                    d["body"]["body"]["objects"].append(b)
            self.zwaveDiscovered = False
            self.bleDiscovered = False
        logging.debug('%s Discovered: %s', ModuleName, str(d))
        if d["body"] != []:
            msg = {"cmd": "msg",
                   "msg": d}
            self.cbSendConcMsg(msg)

    def discover(self):
        logging.debug('%s discover', ModuleName)
        if CB_SIM_LEVEL == '1':
            d = self.simDiscover.discover(isotime())
            msg = {"cmd": "msg",
                   "msg": d}
            logging.debug('%s simulated discover: %s', ModuleName, msg)
            self.cbSendConcMsg(msg)
            return
        # If there are peripherals report any that are not reported rather than discover
        logging.debug('%s CB_PERIPHERALS: %s', ModuleName, CB_PERIPHERALS)
        if CB_PERIPHERALS != "none":
            found = True
            newPeripheral = ''
            logging.debug('%s Checking for peripherals: %s', ModuleName, CB_PERIPHERALS)
            peripherals = CB_PERIPHERALS.split(',')
            peripherals = [p.strip(' ') for p in peripherals]
            for p in peripherals:
                for dev in self.devices:
                    logging.debug('%s peripheral: %s, device: %s', ModuleName, p, dev["adaptor"]["name"])
                    if p in dev["adaptor"]["name"] or p == "none":
                        found = False
                        break
                if found:
                    newPeripheral = p
                    break
            if found:
                d = {}
                d["source"] = self.bridge_id
                d["destination"] = "cb"
                d["time_sent"] = isotime()
                d["body"] = {}
                d["body"]["resource"] = "/api/bridge/v1/device_discovery/"
                d["body"]["verb"] = "patch"
                d["body"]["body"] = {}
                d["body"]["body"]["objects"] = []
                b = {'manufacturer_name': 0, 
                     'protocol': 'peripheral', 
                     'address': '', 
                     'name': newPeripheral,
                     'model_number': 0
                    }
                d["body"]["body"]["objects"].append(b)
                msg = {"cmd": "msg",
                       "msg": d}
                self.cbSendConcMsg(msg)
        if CB_PERIPHERALS == "none" or not found:
            if CB_ZWAVE_BRIDGE:
                self.elFactory["zwave"].sendMsg({"cmd": "discover"})
                self.zwaveDiscovering = False
            if self.bluetooth:
                reactor.callInThread(self.bleDiscover)
            reactor.callInThread(self.usbDiscover)
            self.sendStatusMsg("Follow manufacturer's instructions for device to be connected now.")

    def onZwaveExcluded(self, address):
        logging.debug('%s onZwaveExclude, address: %s', ModuleName, address)
        msg = "No Z-wave device was excluded. No button pressed on device?"
        if address == "" or address == "None":
            msg= "No Z-wave device was excluded.\n Remember some devices need one click and others three. \n Also, devices need to be near the bridge to exclude."
        elif address == "0":
            msg = "Reset a device from a different Z-Wave controller"
        else:
            found = False
            for d in self.devices:
                if d["address"] == address:
                    msg= "Excluded " + d["friendly_name"] + ". Please remove it from the devices list."
                    found = True
                    break
            if not found:
                msg= "Excluded Z-Wave device at address " + address + ".\n Device interview may not have been completed.\n You may need to rerun discover devices?"
        self.sendStatusMsg(msg)

    def zwaveExclude(self):
        logging.debug('%s zwaveExclude', ModuleName)
        if CB_ZWAVE_BRIDGE:
            self.elFactory["zwave"].sendMsg({"cmd": "exclude"})
            self.sendStatusMsg("Follow manufacturer's instructions for Z-wave device to be excluded")
        else:
            self.sendStatusMsg("Bridge does not support Z-wave. Can't exclude")

    def readConfig(self):
        # BEWARE. SOMETIMES CALLED IN A THREAD.
        appRoot = CB_HOME + "/apps/"
        adtRoot = CB_HOME + "/adaptors/"
        if CB_DEV_BRIDGE:
            logging.warning('%s Development user (CB_USERNAME): %s', ModuleName, CB_USERNAME)
            self.devApps = CB_DEV_APPS.split(',')
            self.devApps = [x.strip(' ') for x in self.devApps]
            logging.debug('%s self.devApps: %s', ModuleName, self.devApps)
            self.devAdaptors = CB_DEV_ADAPTORS.split(',')
            self.devAdaptors = [x.strip(' ') for x in self.devAdaptors]
            logging.debug('%s self.devAdaptors: %s', ModuleName, self.devAdaptors)
            if CB_USERNAME == 'none':
                logging.warning('%s CB_DEV_BRIDGE=True, but CB_USERNAME not set, so apps_dev and adaptors_dev not used', ModuleName)
                appRootDev = appRoot
                adtRootDev = adtRoot
            else:   
                appRootDev = "/home/" + CB_USERNAME + "/apps_dev/"
                adtRootDev = "/home/" + CB_USERNAME + "/adaptors_dev/"
            logging.debug('%s appRootDev: %s', ModuleName, appRootDev)
            logging.debug('%s adtRootDev: %s', ModuleName, adtRootDev)
        configFile = CB_CONFIG_DIR + "/bridge.config"
        configRead = False
        try:
            with open(configFile, 'r') as configFile:
                config = json.load(configFile)
                configRead = True
                logging.info('%s Read config', ModuleName)
        except Exception as ex:
            logging.warning('%s No config file exists or file is corrupt', ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            success= False
        if configRead:
            try:
                #self.bridge_id = "BID" + str(config["body"]["body"]["id"])
                self.apps = config["body"]["body"]["apps"]
                self.devices = config["body"]["body"]["devices"]
                success = True
            except Exception as ex:
                logging.error('%s bridge.config appears to be corrupt. Ignoring', ModuleName)
                logging.error("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
                success = False

        if success:
            # Process config to determine routing:
            logging.info('%s Config file for bridge %s read successfully. Processing', ModuleName, self.bridge_id)
            for d in self.devices:
                d["id"] = "DID" + str(d["id"])
                socket = CB_SOCKET_DIR + "SKT-MGR-" + str(d["id"])
                d["adaptor"]["mgrSoc"] = socket
                url = d["adaptor"]["url"]
                split_url = url.split('/')
                if CB_DEV_BRIDGE and d["adaptor"]["name"] in self.devAdaptors:
                    dirName = split_url[-3]
                    d["adaptor"]["exe"] = adtRootDev + dirName + "/" + d["adaptor"]["exe"]
                else:
                    dirName = (split_url[-3] + '-' + split_url[-1])[:-7]
                    d["adaptor"]["exe"] = adtRoot + dirName + "/" + d["adaptor"]["exe"]
                logging.debug('%s exe: %s', ModuleName, d["adaptor"]["exe"])
                logging.debug('%s protocol: %s', ModuleName, d["device"]["protocol"])
                if d["device"]["protocol"] == "zwave":
                    d["adaptor"]["zwave_socket"] =  CB_SOCKET_DIR + "skt-" + d["id"] + "-zwave"
                # Add a apps list to each device adaptor
                d["adaptor"]["apps"] = []
                if d["id"] not in self.idToName:
                    self.idToName.update({d["id"]: d["friendly_name"]})
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["app"]["id"] = "AID" + str(a["app"]["id"])
                url = a["app"]["url"]
                split_url = url.split('/')
                if CB_DEV_BRIDGE and a["app"]["name"] in self.devApps:
                    dirName = split_url[-3]
                    a["app"]["exe"] = appRootDev + dirName + "/" + a["app"]["exe"]
                else:
                    dirName = (split_url[-3] + '-' + split_url[-1])[:-7]
                    a["app"]["exe"] = appRoot + dirName + "/" + a["app"]["exe"]
                logging.debug('%s exe: %s', ModuleName, a["app"]["exe"])
                a["app"]["mgrSoc"] = CB_SOCKET_DIR + "SKT-MGR-" + str(a["app"]["id"])
                a["app"]["concSoc"] = CB_SOCKET_DIR + "SKT-CONC-" + str(a["app"]["id"])
                if a["app"]["id"] not in self.idToName:
                    self.idToName.update({a["app"]["id"]: a["app"]["name"]})
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
            logging.debug("%s idToName: %s", ModuleName, str(self.idToName))
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
        except Exception as ex:
            logging.warning('%s Error extracting %s', ModuleName, tarFile)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
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
        except Exception as ex:
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            logging.warning('%s No version file for %s', ModuleName, elementDir)
            return "error"

    def updateElements(self):
        """
        Directoriies: CB_HOME/apps/<appname>, CB_HOME/adaptors/<adaptorname>.
        Check if appname/adaptorname exist. If not, download app/adaptor.
        If directory does exist, check version file inside & download if changed.
        """
        # THIS METHOD IS IN A THREAD
        updateList = []
        d = CB_HOME + "/adaptors"
        if not os.path.exists(d):
            os.makedirs(d)
        dirs = os.listdir(d)
        for dev in self.devices:
            if CB_DEV_BRIDGE and dev["adaptor"]["name"] in self.devAdaptors:
                logging.debug('%s updateElements. Using %s from adaptors_dev', ModuleName, dev["adaptor"]["name"])
            else:
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
            if CB_DEV_BRIDGE and app["app"]["name"] in self.devApps:
                logging.debug('%s updateElements. Using %s from apps_dev', ModuleName, app["app"]["name"])
            else:
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
            logging.debug('%s Iterating updateList', ModuleName)
            status = self.downloadElement(e)
            if status != "ok":
                reactor.callFromThread(self.sendStatusMsg, status)
        if updateList == []:
            return "Updated. All apps and adaptors already at latest versions"
        else:
            logging.debug('%s updateList != []', ModuleName)
            feedback = "Updated: "
            for a in updateList:
                feedback += " " + a["name"]
            return feedback

    def updateConfig(self, msg):
        # THIS METHOD IS IN A THREAD
        #logging.info('%s Config update received from controller', ModuleName)
        reactor.callFromThread(self.sendStatusMsg, "Updating. This may take a minute")
        #logging.debug('%s %s', ModuleName, str(msg))
        configFile = CB_CONFIG_DIR + "/bridge.config"
        with open(configFile, 'w') as configFile:
            json.dump(msg, configFile)
        success = self.readConfig()
        logging.info('%s Update config, read config status: %s', ModuleName, success)
        if success:
            try:
                status = self.updateElements()
            except Exception as ex:
                logging.warning('%s Update config. Something went badly wrong updating apps and adaptors', ModuleName)
                logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
                status = "Something went badly wrong updating apps and adaptors"
        else:
            status = "Update failed"
            logging.warning('%s Update config. Failed to update ', ModuleName)
        reactor.callFromThread(self.sendStatusMsg, status)
        # Need to give concentrator new config if initial one was without apps
        if self.concNoApps:
            req = {"status": "req-config",
                   "type": "conc"}
            reactor.callFromThread(self.onClientMessage, req)
            self.concNoApps = False

    def upgradeBridge(self, command):
        reactor.callFromThread(self.sendStatusMsg, "Upgrade in progress. Please wait")
        try:
            u = command.split()
            if len(u) == 1:
                upgradeURL = CB_INC_UPGRADE_URL
            elif u[1] == "full":
                upgradeURL = CB_FULL_UPGRADE_URL
            elif u[1] == "dev":
                upgradeURL = CB_DEV_UPGRADE_URL
            else:
                self.sendStatusMsg("Unknown upgrade type. Ignoring")
                return
        except Exception as ex:
            logging.warning('%s Pooblem with upgrade command %s', ModuleName, str(command))
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            self.sendStatusMsg("Bad upgrade command. Allowed options: none|full|dev")
            return
        reactor.callFromThread(self.sendStatusMsg, "Downloading from: " + upgradeURL)
        upgradeStat = ""
        tarFile = CB_HOME + "/bridge_clone.tar.gz"
        logging.debug('%s tarFile: %s', ModuleName, tarFile)
        try:
            urllib.urlretrieve(upgradeURL, tarFile)
        except Exception as ex:
            logging.error('%s Cannot access GitHub file to upgrade', ModuleName)
            logging.error("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            reactor.callFromThread(self.sendStatusMsg, "Cannot access GitHub file to upgrade")
            return
        try:
            subprocess.check_call(["tar", "xfz",  tarFile, "--overwrite", "-C", CB_HOME])
            logging.info('%s Extract tarFile: %s', ModuleName, tarFile)
        except Exception as ex:
            logging.error('%s Unable to extract tarFile %s', ModuleName, tarFile)
            logging.error("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            reactor.callFromThread(self.sendStatusMsg, "Failed to upgrade. Reverting to previous version")
            return
        try:
            status = subprocess.check_output("../../bridge_clone/scripts/cbupgrade.py")
        except Exception as ex:
            logging.error('%s Unable to run upgrade script', ModuleName)
            logging.error("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            reactor.callFromThread(self.sendStatusMsg, "Failed to upgrade. Reverting to previous version")
            return
        bridgeDir = CB_HOME + "/bridge"
        bridgeSave = CB_HOME + "/bridge_save"
        bridgeClone = CB_HOME + "/bridge_clone"
        logging.info('%s Upgrade files: %s %s %s', ModuleName, bridgeDir, bridgeSave, bridgeClone)
        try:
            subprocess.call(["rm", "-rf", bridgeSave])
        except Exception as ex:
            logging.warning('%s Could not remove bridgeSave', ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        try:
            subprocess.call(["mv", bridgeDir, bridgeSave])
            logging.info('%s Moved bridgeDir to bridgeSave', ModuleName)
            subprocess.call(["mv", bridgeClone, bridgeDir])
            logging.info('%s Moved bridgeClone to bridgeDir', ModuleName)
            reactor.callFromThread(self.sendStatusMsg, "Upgrade successful. Restarting")
            reactor.callFromThread(self.cbSendSuperMsg, {"msg": "restart_cbridge"})
        except Exception as ex:
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            reactor.callFromThread(self.sendStatusMsg, "Upgrade failed. Problems moving versions")
    
    def waitToUpgrade(self, command):
        # Call in threaad as it can take some time & watchdog still going
        reactor.callInThread(self.upgradeBridge, command)

    def uploadLog(self, logFile, dropboxPlace, status):
        try:
            f = open(logFile, 'rb')
        except Exception as ex:
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            status = "Could not open log file for upload: " + logFile
        else:
            try:
                response = self.client.put_file(dropboxPlace, f)
                #logging.debug('%s Dropbox log upload response: %s', ModuleName, response)
            except Exception as ex:
                logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
                status = "Could not upload log file: " + logFile
        reactor.callFromThread(self.sendStatusMsg, status)

    def sendLog(self, path, fileName):
        status = "Logfile upload failed"
        access_token = os.getenv('CB_DROPBOX_TOKEN', 'NO_TOKEN')
        logging.info('%s Dropbox access token %s', ModuleName, access_token)
        try:
            self.client = DropboxClient(access_token)
            status = "Log file uploaded OK" 
        except Exception as ex:
            logging.warning('%s Dropbox access token did not work %s', ModuleName, access_token)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            status = "Dropbox access token did not work"
            self.sendStatusMsg(status)
        else:
            hostname = "unknown"
            with open('/etc/hostname', 'r') as hostFile:
                hostname = hostFile.read()
            if hostname.endswith('\n'):
                hostname = hostname[:-1]
            dropboxPlace = '/' + hostname + '-' + fileName
            logging.info('%s Uploading %s to %s', ModuleName, path, dropboxPlace)
            reactor.callInThread(self.uploadLog, path, dropboxPlace, status)

    def doCall(self, cmd):
        try:
            output = subprocess.check_output(cmd, shell=True)
            logging.debug('%s Output from call: %s', ModuleName, output)
        except Exception as ex:
            logging.warning('%s Error in running call: %s', ModuleName, cmd)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            output = "Error in running call"
        reactor.callFromThread(self.sendStatusMsg, output)

    def sendBatteryLevels(self):
        levels = ""
        for b in self.batteryLevels:
            for d in self.devices:
                if b["id"] == d["id"]:
                    levels = levels + d["friendly_name"] + ": " + str(b["battery_level"]) + "%\r\n"
                    break
        if levels == "":
            levels = "No battery level information available at this time"
        self.sendStatusMsg(levels)

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
            logging.warning('%s Unrecognised command received from controller', ModuleName)
            return
        else:
            if msg["body"]["connected"] == True:
                if self.controllerConnected == False:
                    self.notifyApps(True)
                self.controllerConnected = True
                self.disconnectedCount = 0
            else:
                if self.controllerConnected == True:
                    self.notifyApps(False)
                self.controllerConnected = False
                self.disconnectedCount += 1
 
    def onControlMessage(self, msg):
        if not "body" in msg: 
            logging.error('%s msg received from controller with no "body" key', ModuleName)
            self.sendStatusMsg("Error. message received from controller with no body key")
            return 
        if self.bridge_id == "unconfigured":
            if "destination" in msg:
                logging.info('%s No BID from bridge.config - used %s from incoming message', ModuleName, msg["destination"])
                self.bridge_id = msg["destination"]
        if "connected" in msg["body"]:
            self.processConduitStatus(msg)
            return
        logging.debug("%s Received from controller: %s", ModuleName, json.dumps(msg, indent=4))
        if "command" in msg["body"]:
            command = msg["body"]["command"]
            if command == "start":
                if self.configured:
                    if self.state == "stopped":
                        logging.info('%s Starting adaptors and apps', ModuleName)
                        self.startAll()
                    else:
                        self.sendStatusMsg("Already starting or running. Start command ignored.")
                else:
                    logging.warning('%s Cannot start adaptors and apps. Please run discovery', ModuleName)
                    self.sendStatusMsg("Start command received with no apps and adaptors")
            elif command == "discover":
                if self.state != "stopped":
                    self.stopApps()
                    reactor.callLater(APP_STOP_DELAY, self.killAppProcs)
                    reactor.callLater(APP_STOP_DELAY + MIN_DELAY, self.discover)
                else:
                    reactor.callLater(MIN_DELAY, self.discover)
            elif command == "restart":
                logging.info('%s Received restart command', ModuleName)
                self.cbSendSuperMsg({"msg": "restart"})
                self.restarting = True
                self.sendStatusMsg("restarting")
            elif command == "reboot":
                logging.info('%s Received reboot command', ModuleName)
                self.cbSendSuperMsg({"msg": "reboot"})
                self.sendStatusMsg("Preparing to reboot")
            elif command == "stop":
                if self.state != "stopping" and self.state != "stopped":
                    self.stopApps()
                    reactor.callLater(APP_STOP_DELAY, self.killAppProcs)
                else:
                    self.sendStatusMsg("Already stopped or stopping. Stop command ignored.")
            elif command.startswith("upgrade"):
                if self.state != "stopped":
                    self.stopApps()
                reactor.callLater(APP_STOP_DELAY, self.killAppProcs)
                reactor.callLater(APP_STOP_DELAY + MIN_DELAY, self.waitToUpgrade, command)
            elif command == "sendlog" or command == "send_log":
                self.sendLog(CB_CONFIG_DIR + '/bridge.log', 'bridge.log')
            elif command == "battery":
                self.sendBatteryLevels()
            elif command.startswith("call"):
                # Need to call in thread is case it hangs
                reactor.callInThread(self.doCall, command[5:])
            elif command.startswith("upload"):
                # Need to call in thread is case it hangs
                path = command[7:]
                fileName = path.split('/')[-1]
                reactor.callInThread(self.sendLog, path, fileName)
            elif command == "update_config" or command == "update":
                req = {"cmd": "msg",
                       "msg": {"source": self.bridge_id,
                               "destination": "cb",
                               "time_sent": isotime(),
                               "body": {
                                        "resource": "/api/bridge/v1/current_bridge/bridge",
                                        "verb": "get"
                                       }
                              }
                      }
                self.cbSendConcMsg(req)
            elif command == "z-exclude" or command == "z_exclude":
                self.zwaveExclude()
            elif command.startswith("action"):
                try:
                    action = command.split()
                    found = False
                    for i in self.idToName:
                        if self.idToName[i] == action[1]:
                            found = True
                            self.cbSendMsg({"cmd": "action",
                                            "action": action[2]}, 
                                           i)
                            logging.debug('%s action, sent %s to %s', ModuleName, action[2], self.idToName[i])
                            self.sendStatusMsg("Sent " + action[2] + " to " + self.idToName[i])
                            break
                    if not found:
                        self.sendStatusMsg("Action requested for unrecognised app or device")
                except Exception as ex:
                    logging.warning('%s Badly formed action command %s', ModuleName, str(action))
                    logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
                    self.sendStatusMsg("Usage: action <device name> <action>")
            else:
                logging.warning('%s Unrecognised command message received from controller: %s', ModuleName, msg)
                self.sendStatusMsg("Unrecognised command message received from controller")
        elif "resource" in msg["body"]:
            # Call in thread to prevent problems with blocking
            if msg["body"]["resource"] == "/api/bridge/v1/current_bridge/bridge":
                reactor.callInThread(self.updateConfig, msg)
            elif msg["body"]["resource"] == "/api/bridge/v1/discovered_device/":
                logging.info('%s Received discovered_device message from controller', ModuleName)
            else:
                logging.info('%s Unrecognised resource in message received from controller', ModuleName)
                self.sendStatusMsg("Unrecognised resource in message received from controller")
        else:
            logging.info('%s No command or resource field in body of server message', ModuleName)
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
                except Exception as ex:
                    logging.warning('%s Could not send stop message to  %s', ModuleName, a)
                    logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        self.cbSendSuperMsg({"msg": "end of stopApps"})

    def killAppProcs(self):
        # If not configured there will be no app processes & no mgrSocs
        if self.configured:
            # Stop listing on sockets
            mgrSocs = self.listMgrSocs()
            for a in mgrSocs:
                try:
                    logging.debug('%s Stop listening on %s', ModuleName, a)
                    self.appListen[a].stopListening()
                except Exception as ex:
                    logging.debug('%s Unable to stop listening on: %s', ModuleName, a)
                    logging.debug("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            # In case apps & adaptors have not shut down, kill their processes.
            for p in self.appProcs:
                try:
                    p.kill()
                except:
                    logging.debug('%s No process to kill', ModuleName)
            self.removeSecondarySockets()
            # In case some adaptors have not killed gatttool processes:
            try:
                subprocess.call(["killall", "gatttool"])
            except:
                pass
            self.states("stopped")

    def stopAll(self):
        self.sendStatusMsg("Disconnecting. Goodbye, back soon ...")
        logging.info('%s Stopping concentrator', ModuleName)
        if CB_ZWAVE_BRIDGE:
            self.elFactory["zwave"].sendMsg({"cmd": "stop"})
        self.cbSendConcMsg({"cmd": "stop"})
        # Give concentrator a change to stop before killing it and its sockets
        reactor.callLater(MIN_DELAY*2, self.stopManager)

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
        now = str(time.strftime('%H:%M:%S', time.localtime(time.time())))
        msg = {"cmd": "msg",
               "msg": {"source": self.bridge_id,
                       "destination": "broadcast",
                       "time_sent": isotime(),
                       "body": {
                                 "status": now + ' ' + status
                               }
                      }
              }
        logging.debug('%s Sending status message: %s', ModuleName, msg)
        self.cbSendConcMsg(msg)
 
    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def cbSendConcMsg(self, msg):
        try:
            self.elFactory["conc"].sendMsg(msg)
        except Exception as ex:
            logging.warning('%s Appear to be trying to send a message to concentrator before connected: %s', ModuleName, msg)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))

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
                        self.restarting = True
                        break
                else:
                    self.elements[e] = False
        reactor.callLater(ELEMENT_WATCHDOG_INTERVAL, self.elementWatchdog)
        if self.firstWatchdog:
            l = task.LoopingCall(self.pollElement)
            l.start(ELEMENT_POLL_INTERVAL) # call every second
            self.firstWatchdog = False

    def pollElement(self):
        for e in self.elements:
            if self.elements[e] == False:
                #logging.debug('%s pollElement, elements: %s', ModuleName, e)
                try:
                    if e == "conc":
                        self.cbSendConcMsg({"cmd": "status"})
                    elif e == "zwave":
                        self.elFactory["zwave"].sendMsg({"cmd": "status"})
                    else:
                        self.cbSendMsg({"cmd": "status"}, e)
                except Exception as inst:
                    logging.warning("%s pollElement. Could not send message to: %s", ModuleName, e)
                    logging.warning("%s Exception: %s %s", ModuleName, type(inst), str(inst.args))

    def onUserMessage(self, msg):
        if "body" in msg:
            userMsg = msg["body"]
        else:
            userMsg = "No log message provided" 
            logging.warning('%s %s', ModuleName, userMsg)
        self.sendStatusMsg(userMsg)

    def onLogMessage(self, msg):
        if "level" in msg:
            level = msg["level"]
        else:
            level = "unknown"
        if "body" in msg:
            logMsg = msg["body"]
        else:
            logMsg = "No log message provided" 
        name = self.idToName[msg["id"]]
        if level == "error":
            logging.error("%s %s", name, logMsg)
        elif level == "warning":
            logging.warning("%s %s", name, logMsg)
        elif level == "info":
            logging.info("%s %s", name, logMsg)
        elif level == "debug":
            logging.debug("%s %s", name, logMsg)
        else:
            logging.debug("Unknown logging level: %s %s", name, logMsg)

    def notifyApps(self, connected):
        for a in self.appConfigured:
            msg = {
                   "cmd": "status",
                   "status": connected
                  }
            self.cbSendMsg(msg, a)

    def onClientMessage(self, msg):
        #logging.debug('%s Received msg; %s', ModuleName, msg)
        # Set watchdog flag
        if not "status" in msg:
            logging.warning('%s No status key in message from client; %s', ModuleName, msg)
            return
        if msg["status"] == "control_msg":
            del msg["status"]
            self.onControlMessage(msg)
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
                                                       "bridge_id": self.bridge_id,
                                                       "connected": self.controllerConnected,
                                                       "concentrator": conc}}
                                #logging.debug('%s Response: %s %s', ModuleName, msg['id'], response)
                                self.cbSendMsg(response, msg["id"])
                                self.appConfigured.append(msg["id"])
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
                                "config": {"bridge_id": self.bridge_id}
                               }
                logging.debug('%s Sending config to conc:  %s', ModuleName, response)
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
            self.onLogMessage(msg)
        elif msg["status"] == "user_message":
            self.onUserMessage(msg)
        elif msg["status"] == "discovered":
            if msg["id"] == "zwave":
                self.onZwaveDiscovered(msg)
            else:
                logging.warning('%s Discovered message from unexpected source: %s', ModuleName, msg["id"])
        elif msg["status"] == "discovering":
            if msg["id"] == "zwave":
                self.onZwaveDiscovering(msg)
            else:
                logging.warning('%s Discovering message from unexpected source: %s', ModuleName, msg["id"])
        elif msg["status"] == "excluded":
            if msg["id"] == "zwave":
                self.onZwaveExcluded(msg["body"])
            else:
                logging.warning('%s Excluded message from unexpected source: %s', ModuleName, msg["id"])
        elif msg["status"] == "state":
            if "state" in msg:
                logging.debug('%s %s %s', ModuleName, msg["id"], msg["state"])
            else:
                logging.warning('%s Received state message from %s with no state', ModuleName, msg["id"])
        elif msg["status"] == "battery_level":
            if "battery_level" in msg:
                for d in self.batteryLevels:
                    if d["id"] == msg["id"]:
                        d["battery_level"] = msg["battery_level"]
                        break
                else:
                    self.batteryLevels.append({"id": msg["id"], "battery_level": msg["battery_level"]})
            else:
                logging.warning('%s Received battery_level message from %s with no battery_level', ModuleName, msg["id"])
        elif msg["status"] == "error":
            if not self.restarting:
                logging.warning('%s Error status received from %s. Restarting', ModuleName, msg["id"])
                self.sendStatusMsg("Error status received from " + msg["id"] + " - Restarting")
                self.cbSendSuperMsg({"msg": "restart"})
                self.restarting = True
        elif msg["status"] != "ok":
            logging.debug('%s Messagge from client: %s', ModuleName, msg)
 
if __name__ == '__main__':
    m = ManageBridge()
