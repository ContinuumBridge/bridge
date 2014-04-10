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
        self.running = False
        self.stopping = False
        self.concNoApps = False
        self.elements = {}
        self.appProcs = []
        self.concConfig = []
        self.cbFactory = {} 
        self.appListen = {}
        status = self.readConfig()
        logging.info('%s Status: %s', ModuleName, status)
        self.initBridge()

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
        logging.info('%s Bridge running', ModuleName)
        self.running = True

    def startAll(self):
        self.stopping = False
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
            logging.error('%s App %s failed to start', ModuleName, id)

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
            msg = {"cmd": "msg",
                          "msg": {"message": "status",
                                  "channel": "bridge_manager",
                                  "body": "Unable to load output from discovery.py" 
                                 }
                  }
            reactor.callFromThread(self.cbSendConcMsg, msg)
        else:   
            self.discoveredDevices["message"] = "request"
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
        appRoot = CB_BRIDGE_ROOT + "/apps/"
        adtRoot = CB_BRIDGE_ROOT + "/adaptors/"
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
            self.configured = False
        if configRead:
            try:
                self.apps = config["body"]["apps"]
                self.devices = config["body"]["devices"]
                self.configured = True
            except:
                self.configured = False
                logging.error('%s bridge.config appears to be corrupt. Ignoring', ModuleName)

        if self.configured:
            # Process config to determine routing:
            for d in self.devices:
                d["id"] = "dev" + str(d["id"])
                socket = CB_SOCKET_DIR + "skt-mgr-" + str(d["id"])
                d["adaptor"]["mgrSoc"] = socket
                d["adaptor"]["exe"] = adtRoot + \
                    d["adaptor"]["exe"]
                # Add a apps list to each device adaptor
                d["adaptor"]["apps"] = []
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["app"]["id"] = "app" + str(a["app"]["id"])
                a["app"]["exe"] = appRoot + a["app"]["exe"]
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
        if self.configured:
            logging.info('%s Config information processed', ModuleName)
            logging.info('%s Apps:', ModuleName)
            logging.info('%s %s', ModuleName, str(self.apps))
            logging.info('%s', ModuleName)
            logging.info('%s Devices:', ModuleName)
            logging.info('%s %s', ModuleName, str(self.devices))
            logging.info('%s', ModuleName)
        return "Configured"
    
    def updateConfig(self, msg):
        logging.debug('%s Config received from controller:', ModuleName)
        logging.debug('%s %s', ModuleName, str(msg))
        configFile = CB_CONFIG_DIR + "/bridge.config"
        with open(configFile, 'w') as configFile:
            json.dump(msg, configFile)
        status = self.readConfig()
        logging.info('%s %s', ModuleName, status)

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
        msg = {"cmd": "msg",
               "msg": {"message": "status",
                       "channel": "bridge_manager",
                       "body": upgradeStat
                      }
              }
        self.cbSendConcMsg(msg)
        if okToReboot:
            resp = {"msg": "reboot"}
            self.cbSendSuperMsg(resp)

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
        msg = {"cmd": "msg",
               "msg": {"message": "status",
                       "channel": "bridge_manager",
                        "body": status 
                      }
              }
        self.cbSendConcMsg(msg)

    def doCall(self, cmd):
        try:
            output = subprocess.check_output(cmd, shell=True)
            logging.debug('%s Output from call: %s', ModuleName, output)
        except:
            logging.warning('%s Error in running call: %s', ModuleName, cmd)
            output = "Error in running call"
        msg = {"cmd": "msg",
               "msg": {"message": "status",
                       "channel": "bridge_manager",
                        "body": output 
                      }
              }
        reactor.callFromThread(self.cbSendConcMsg, msg)

    def processSuper(self, msg):
        """  watchdog. Replies with status=ok or a restart/reboot command. """
        if msg["msg"] == "stopall":
            resp = {"msg": "status",
                    "status": "stopping"
                   }
            self.cbSendSuperMsg(resp)
            reactor.callLater(0.2, self.stopAll)
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
        if not "message" in msg: 
            logging.error('%s msg received from controller with no "message" key', ModuleName)
            msg = {"cmd": "msg",
                   "msg": {"message": "status",
                           "channel": "bridge_manager",
                           "body": "Error. message received from controller with no message key"
                          }
                  }
            self.cbSendConcMsg(msg)
            return 
        if msg["message"] == "command":
            if not "body" in msg:
                logging.error('%s command message received from controller with no body', ModuleName)
                msg = {"cmd": "msg",
                       "msg": {"message": "status",
                               "channel": "bridge_manager",
                               "body": "Error. command message received from controller with no body"
                              }
                      }
                self.cbSendConcMsg(msg)
                return 
            if msg["body"] == "start":
                if self.configured:
                    logging.info('%s Starting adaptors and apps', ModuleName)
                    self.startAll()
                else:
                    logging.warning('%s Cannot start adaptors and apps. Please run discovery', ModuleName)
                    msg = {"cmd": "msg",
                           "msg": {"message": "status",
                                   "channel": "bridge_manager",
                                   "body": "Start command received with no apps and adaptors"
                                  }
                          }
                    self.cbSendConcMsg(msg)
            elif msg["body"] == "discover":
                if self.configured and self.running and not self.stopping:
                    self.stopApps()
                    reactor.callLater(8, self.discover)
                else:
                    self.discover()
            elif msg["body"] == "restart":
                logging.info('%s Received restart command', ModuleName)
                resp = {"msg": "restart"}
                self.cbSendSuperMsg(resp)
                msg = {"cmd": "msg",
                       "msg": {"message": "status",
                               "channel": "bridge_manager",
                               "body": "restarting"
                              }
                      }
                self.cbSendConcMsg(msg)
            elif msg["body"] == "reboot":
                logging.info('%s Received reboot command', ModuleName)
                resp = {"msg": "reboot"}
                self.cbSendSuperMsg(resp)
                msg = {"cmd": "msg",
                       "msg": {"message": "status",
                               "channel": "bridge_manager",
                               "body": "rebooting"
                              }
                      }
                self.cbSendConcMsg(msg)
            elif msg["body"] == "stop":
                if self.configured and self.running and not self.stopping:
                    self.stopApps()
            elif msg["body"] == "stop_manager" or msg["body"] == "stopall":
                self.stopAll()
            elif msg["body"] == "upgrade":
                self.upgradeBridge()
            elif msg["body"] == "sendlog" or msg["body"] == "send_log":
                self.sendLog()
            elif msg["body"].startswith("call"):
                # Need to call in thread is case it hangs
                reactor.callInThread(self.doCall, msg["body"][5:])
            elif msg["body"] == "update_config" or msg["body"] == "update":
                req = {"cmd": "msg",
                       "msg": {"message": "request",
                               "channel": "bridge_manager",
                               "request": "get",
                               "url": "/api/bridge/v1/current_bridge/bridge"}
                      }
                self.cbSendConcMsg(req)
            else:
                logging.warning('%s Unrecognised message received from server: %s', ModuleName, msg)
                msg = {"cmd": "msg",
                       "msg": {"message": "status",
                               "channel": "bridge_manager",
                               "body": "Unrecognised command received from controller"
                              }
                      }
                self.cbSendConcMsg(msg)
        elif msg["message"] == "response":
            self.updateConfig(msg)
            # Need to give concentrator new config if initial one was without apps
            if self.concNoApps:
                req = {"status": "req-config",
                       "type": "conc"}
                self.processClient(req)
                self.concNoApps = False
        elif msg["message"] == "status":
            if not "source" in msg:
                logging.warning('%s Unrecognised command received from controller: %s', ModuleName, msg)
                return
            else:
                self.processConduitStatus(msg)
        else:
            logging.info('%s Unrecognised message received from server: %s', ModuleName, msg)
            msg = {"cmd": "msg",
                   "msg": {"message": "status",
                           "channel": "bridge_manager",
                           "body": "Unrecognised message received from controller"
                          }
                  }
            self.cbSendConcMsg(msg)
 
    def stopAll(self):
        if self.configured and self.running and not self.stopping:
            logging.info('%s Processing stop. Stopping apps', ModuleName)
            self.stopApps()
            reactor.callLater(21, self.stopConcentrator)
        else:
            self.stopConcentrator()
 
    def stopConcentrator(self):
        """ Kills concentrator & nodejs processes, removes sockets & kills itself """
        logging.info('%s Stopping concentrator', ModuleName)
        msg = {"cmd": "stop"}
        self.cbSendConcMsg(msg)
        # Give concentrator a change to stop before killing it and its sockets
        reactor.callLater(1, self.stopManager)

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
        logging.info('%s Stopping reactor', ModuleName)
        reactor.stop()
        sys.exit

    def stopApps(self):
        """ Asks apps & adaptors to clean up nicely and die. """
        logging.info('%s Stopping apps and adaptors', ModuleName)
        self.stopping = True
        mgrSocs = self.listMgrSocs()
        for a in mgrSocs:
            msg = {"cmd": "stop"}
            logging.info('%s Stopping %s', ModuleName, a)
            self.cbSendMsg(msg, a)
        self.running = False
        reactor.callLater(20, self.killAppProcs)

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
        msg = {"cmd": "msg",
               "msg": {"message": "status",
                       "channel": "bridge_manager",
                       "body": "apps_stopped"
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
        for e in self.elements:
            if self.elements[e]== False:
                if e != "conc":
                    logging.warning('%s %s has not communicated within watchdog interval', ModuleName, e)
                    body = "Watchdog timeout for " + e + " - Restarting"
                    resp = {"cmd": "msg",
                            "msg": {"message": "status",
                                    "channel": "bridge_manager",
                                    "body": body
                                   }
                           }
                    self.cbSendConcMsg(resp)
                    superMsg = {"msg": "restart"}
                    self.cbSendSuperMsg(superMsg)
                    break
            else:
                logging.debug('%s %s resetting watchdog', ModuleName, e)
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
                                            "config": {"adts": a["device_permissions"],
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
            status = {"cmd": "msg",
                      "msg": {"message": "status",
                              "channel": "bridge_manager",
                              "body": log
                             }
                     }
            self.cbSendConcMsg(msg)
        elif msg["status"] == "state":
            if "state" in msg:
                logging.debug('%s %s %s', ModuleName, msg["id"], msg["state"])
            else:
                logging.warning('%s Received state message from %s with no state', ModuleName, msg["id"])
        elif msg["status"] == "error":
                logging.warning('%s Error status received from %s. Restarting', ModuleName, msg["id"])
                body = "Error status received from " + msg["id"] + " - Restarting"
                resp = {"cmd": "msg",
                        "msg": {"message": "status",
                                "channel": "bridge_manager",
                                "body": body
                               }
                       }
                self.cbSendConcMsg(resp)
                superMsg = {"msg": "restart"}
                self.cbSendSuperMsg(superMsg)
 
if __name__ == '__main__':
    m = ManageBridge()
