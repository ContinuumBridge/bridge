#!/usr/bin/env python
# cbanager.py
# Copyright (C) ContinuumBridge Limited, 2013-14 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Bridge Manager      "
id = "manager"

import sys
import time
import os
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

class ManageBridge:

    def __init__(self):
        """ apps and adts data structures are stored in a local file.
        """
        self.bridgeRoot = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
        print ModuleName, "CB_BRIDGE_ROOT = ", self.bridgeRoot
        self.noCloud = os.getenv('CB_NO_CLOUD', False)
        print ModuleName, "CB_NO_CLOUD = ", self.noCloud
        self.sim = os.getenv('CB_SIM_LEVEL', '0')
        print ModuleName, "CB_SIM = ", self.sim
        self.controllerAddr = os.getenv('CB_CONTROLLER_ADDR', '54.194.28.63')
        print ModuleName, "CB_CONTROLLER_ADDR = ", self.controllerAddr
        self.email = "cde5fb1645e74314a3e6841a4df0828d@continuumbridge.com"
        self.password = "zqN17m94GftDvNiWNGls+6tyxryCJFWxzWC5hs/fTmF7YXn4i8eogVa/HzwK5fK2"
        self.discovered = False
        self.configured = False
        self.reqSync = False
        self.running = False
        self.stopping = False
        self.concNoApps = False
        self.appProcs = []
        self.concConfig = []
        self.cbFactory = {} 
        self.appListen = {}
        status = self.readConfig()
        print ModuleName, status
        self.initBridge()

    def initBridge(self):
        if self.noCloud != "True":
            print ModuleName, "Bridge Manager Starting JS Concentrator"
            exe = "nodejs"
            path = self.bridgeRoot + "/nodejs/index.js"
            try:
                self.nodejsProc = subprocess.Popen([exe, path, self.controllerAddr, \
                                                    self.email, self.password])
                print ModuleName, "Started node.js"
            except:
                print ModuleName, "node.js failed to start. exe = ", exe
        else:
            print ModuleName, "Running without Cloud Server"
        # Give time for node interface to start
        time.sleep(2)

        if self.configured:
            reactor.callLater(1, self.startAll)
        self.startConcentrator()
        reactor.run()

    def listMgrSocs(self):
        mgrSocs = {}
        for d in self.devices:
            mgrSocs[d["adaptor_install"][0]["id"]] = d["adaptor_install"][0]["mgrSoc"]
        for a in self.apps:
            mgrSocs[a["app"]["id"]] = a["app"]["mgrSoc"]
        return mgrSocs

    def startConcentrator(self):
        # Open a socket for communicating with the concentrator
        s = "skt-mgr-conc"
        try:
            os.remove(s)
        except:
            pass
        try:
            self.cbConcFactory = CbServerFactory(self.processClient)
            self.concListen = reactor.listenUNIX(s, self.cbConcFactory, backlog=4)
            print ModuleName, "Opened manager socket ", s
        except:
            print ModuleName, "Socket already exits: ", s

        # Now start the concentrator in a subprocess
        exe = self.concPath
        id = "conc"
        mgrSoc = "skt-mgr-conc"
        try:
            self.concProc = subprocess.Popen([exe, mgrSoc, id])
            print ModuleName, "Started concentrator"
        except:
            print ModuleName, "Concentrator failed to start"

        # Initiate comms with supervisor, which started the manager in the first place
        s = "skt-super-mgr"
        initMsg = {"id": "manager",
                   "msg": "status",
                   "status": "ok"} 
        #try:
        self.cbSupervisorFactory = CbClientFactory(self.processSuper, initMsg)
        reactor.connectUNIX(s, self.cbSupervisorFactory, timeout=10)
        print ModuleName, "Opened supervisor socket ", s
        #except:
            #print ModuleName, "Cannot open supervisor socket ", s

    def startApps(self):
        for a in self.apps:
            try:
                id = a["app"]["id"]
                exe = a["app"]["exe"]
                mgrSoc = a["app"]["mgrSoc"]
                p = subprocess.Popen([exe, mgrSoc, id])
                self.appProcs.append(p)
                print ModuleName, id, " started"
            except:
                print ModuleName, id, " failed to start"
        # Give time for everything to start before we consider ourselves running
        reactor.callLater(10, self.setRunning)

    def setRunning(self):
        print ModuleName, "Bridge running"
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
                print ModuleName, "Opened manager socket ", s,  mgrSocs[s]
            except:
                print ModuleName, "Manager socket already exits: ", s, mgrSocs[s]

        # Start adaptors
        for d in self.devices:
            exe = d["adaptor_install"][0]["adaptor"]["exe"]
            fName = d["friendly_name"]
            id = d["adaptor_install"][0]["id"]
            mgrSoc = d["adaptor_install"][0]["mgrSoc"]
            try:
                p = subprocess.Popen([exe, mgrSoc, id])
                self.appProcs.append(p)
                print ModuleName, "Started adaptor ", fName, " ID: ", id
                # Give time for adaptor to start before starting the next one
                time.sleep(2)
            except:
                print ModuleName, "Adaptor ", fName, " failed to start"
                print ModuleName, "Params: ", exe, id, mgrSoc
                time.sleep(2)

        # Give time for all adaptors to start before starting apps
        reactor.callLater(5, self.startApps)

    def doDiscover(self):
        self.discoveredDevices = {}
        exe = self.bridgeRoot + "/manager/discovery.py"
        protocol = "btle"
        output = subprocess.check_output([exe, protocol, self.sim])
        print ModuleName, "Discover output = ", output
        discOutput = json.loads(output)
        self.discoveredDevices["msg"] = "req"
        self.discoveredDevices["verb"] = "post"
        self.discoveredDevices["uri"] = "/api/v1/device_discovery"
        self.discoveredDevices["body"] = []
        if self.configured:
            for d in discOutput["body"]:
                addrFound = False
                if d["protocol"] == "btle":
                    for oldDev in self.devices:
                       if oldDev["adaptor_install"][0]["adaptor"]["protocol"] == "btle": 
                           if d["mac_addr"] == oldDev["mac_addr"]:
                               addrFound = True
                if addrFound == False:
                    self.discoveredDevices["body"].append(d)  
        else:
            for d in discOutput["body"]:
                self.discoveredDevices["body"].append(d)  
        print ModuleName, "Discovered devices:"
        print ModuleName, self.discoveredDevices
        msg = {"cmd": "msg",
               "msg": self.discoveredDevices}
        reactor.callFromThread(self.cbSendConcMsg, msg)
        self.discovered = True

    def discover(self):
        # Call in thread so that manager can still process other messages
        reactor.callInThread(self.doDiscover)

    def readConfig(self):
        appRoot = self.bridgeRoot + "/apps/"
        adtRoot = self.bridgeRoot + "/adaptors/"
        self.concPath = self.bridgeRoot + "/concentrator/concentrator.py"
        configRead = False
        try:
            with open('bridge.config', 'r') as configFile:
                config = json.load(configFile)
                configRead = True
                print ModuleName, "readConfig"
                pprint(config)
        except:
            print ModuleName, "Warning. No config file exists"
            self.configured = False
        if configRead:
            self.apps = config["body"]["apps"]
            self.devices = config["body"]["devices"]
            self.configured = True

        if self.configured:
            # Process config to determine routing:
            for d in self.devices:
                d["adaptor_install"][0]["id"] = "dev" + str(d["adaptor_install"][0]["id"])
                socket = "skt-mgr-" + str(d["adaptor_install"][0]["id"])
                d["adaptor_install"][0]["mgrSoc"] = socket
                d["adaptor_install"][0]["adaptor"]["exe"] = adtRoot + \
                    d["adaptor_install"][0]["adaptor"]["exe"]
                # Add a apps list to each device adaptor
                d["adaptor_install"][0]["apps"] = []
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["app"]["id"] = "app" + str(a["app"]["id"])
                a["app"]["exe"] = appRoot + a["app"]["exe"]
                a["app"]["mgrSoc"] = "skt-mgr-" + str(a["app"]["id"])
                a["app"]["concSoc"] = "skt-conc-" + str(a["app"]["id"])
                for appDev in a["device_permissions"]:
                    uri = appDev["device_install"]
                    for d in self.devices: 
                        if d["adaptor_install"][0]["resource_uri"] == uri:
                            socket = "skt-" \
                                + d["adaptor_install"][0]["id"] + "-" + a["app"]["id"]
                            d["adaptor_install"][0]["apps"].append(
                                                    {"adtSoc": socket,
                                                     "name": a["app"]["name"],
                                                     "id": a["app"]["id"]
                                                    }) 
                            appDev["adtSoc"] = socket
                            appDev["id"] = d["adaptor_install"][0]["id"]
                            appDev["name"] = d["adaptor_install"][0]["adaptor"]["name"]
                            appDev["friendly_name"] = \
                                d["friendly_name"]
                            appDev["adtSoc"] = socket
                            break
        if self.configured:
            print ModuleName, "Config information processed:"
            print ModuleName, "Apps:"
            pprint(self.apps)
            print ""
            print ModuleName, "Devices:"
            pprint(self.devices)
            print ""
        return "Configured"
    
    def updateConfig(self, msg):
        print ModuleName, "Config received from controller:"
        pprint(msg)
        with open('bridge.config', 'w') as configFile:
            json.dump(msg, configFile)
        status = self.readConfig()
        print ModuleName, status

    def processSuper(self, msg):
        """ A simple watchdog. Just replies with ok every time it gets a message. """
        if msg["msg"] == "status":
            if msg["status"] == "ok":
                resp = {"msg": "status",
                        "status": "ok"
                       }
                self.cbSendSuperMsg("resp")
        elif msg["msg"] == "stopall":
            resp = {"msg": "status",
                    "status": "stopping"
                   }
            self.cbSendSuperMsg("resp")
            reactor.callLater(0.2, self.stopAll)

    def processControlMsg(self, msg):
        print ModuleName, "Controller msg = ", msg
        if msg["msg"] == "cmd":
            if msg["body"] == "start":
                if self.configured:
                    print ModuleName, "starting adaptors and apps"
                    self.startAll()
                else:
                    print ModuleName, "Can't start adaptors & apps"
                    print ModuleName, "Please run discovery"
                    msg = {"cmd": "msg",
                           "msg": {"msg": "status",
                                   "channel": "bridge_manager",
                                   "body": "start_req_with_no_apps_installed"
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
                print ModuleName, "Received restart command"
            elif msg["body"] == "reboot":
                print ModuleName, "Received reboot command"
            elif msg["body"] == "stop":
                if self.configured and self.running and not self.stopping:
                    self.stopApps()
            elif msg["body"] == "stop_manager" or msg["body"] == "stopall":
                self.stopAll()
            elif msg["body"] == "update_config":
                req = {"cmd": "msg",
                       "msg": {"msg": "req",
                               "channel": "bridge_manager",
                               "verb": "get",
                               "uri": "/api/v1/current_bridge/bridge"}
                      }
                self.cbSendConcMsg(req)
        elif msg["msg"] == "response":
            self.updateConfig(msg)
            # Need to give concentrator new config if initial one was without apps
            if self.concNoApps:
                req = {"status": "req-config",
                       "type": "conc"}
                self.processClient(req)
                self.concNoApps = False
        else:
            print ModuleName, "Received from server: ", msg

    def stopAll(self):
        if self.configured and self.running and not self.stopping:
            print ModuleName, "Processing stop. Stopping apps"
            self.stopApps()
            reactor.callLater(10, self.stopConcentrator)
        else:
            self.stopConcentrator()
 
    def stopConcentrator(self):
        """ Kills concentrator & nodejs processes, removes sockets & kills itself """
        print ModuleName, "Stopping concentrator"
        msg = {"cmd": "stop"}
        self.cbSendConcMsg(msg)
        # Give concentrator a change to stop before killing it and its sockets
        reactor.callLater(1, self.stopManager)

    def stopManager(self):
        self.concListen.stopListening()
        try:
            self.concProc.kill()
        except:
            print ModuleName, "No concentrator process to kill"
        try:
            self.nodejsProc.kill()
        except:
            print ModuleName, "No node.js process to kill"
        for soc in self.concConfig:
            socket = soc["appConcSoc"]
            try:
                os.remove(socket) 
                print ModuleName, socket, " removed"
            except:
                print ModuleName, socket, " already removed"
        print ModuleName, "Stopping reactor"
        try:
            # try/except just to suppress errors due to removed sockets
            reactor.stop()
        except:
            pass
        sys.exit()

    def stopApps(self):
        """ Asks apps & adaptors to clean up nicely and die. """
        print ModuleName, "Stopping apps and adaptors"
        self.stopping = True
        mgrSocs = self.listMgrSocs()
        for a in mgrSocs:
            msg = {"cmd": "stop"}
            self.cbSendMsg(msg, a)
        self.running = False
        reactor.callLater(8, self.killAppProcs)

    def killAppProcs(self):
        # Stop listing on sockets
        mgrSocs = self.listMgrSocs()
        for a in mgrSocs:
           print ModuleName, "Stop listening on ", a
           self.appListen[a].stopListening()
        # In case apps & adaptors have not shut down, kill their processes.
        for p in self.appProcs:
            try:
                p.kill()
            except:
                print ModuleName, "No process to kill"
        for a in self.apps:
            for appDev in a["device_permissions"]:
                socket = appDev["adtSoc"]
                try:
                    os.remove(socket) 
                    print ModuleName, socket, " removed"
                except:
                    print ModuleName, socket, " already removed"
        msg = {"cmd": "msg",
               "msg": {"msg": "status",
                       "channel": "bridge_manager",
                       "body": "apps_stopped"
                      }
              }
        self.cbSendConcMsg(msg)
 
    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def cbSendConcMsg(self, msg):
        self.cbConcFactory.sendMsg(msg)

    def cbSendSuperMsg(self, msg):
        self.cbSupervisorFactory.sendMsg(msg)

    def processClient(self, msg):
        print ModuleName, "Received msg from client", msg
        if msg["status"] == "control_msg":
            del msg["status"]
            self.processControlMsg(msg)
        elif msg["status"] == "req-config":
            if msg["type"] == "app":
                for a in self.apps:
                    if a["app"]["id"] == msg["id"]:
                        for c in self.concConfig:
                            if c["id"] == msg["id"]:
                                conc = c["appConcSoc"]
                                response = {"cmd": "config",
                                            "sim": self.sim,
                                            "config": {"adts": a["device_permissions"],
                                                       "concentrator": conc}}
                                self.cbSendMsg(response, msg["id"])
                                break
                        break
            elif msg["type"] == "adt": 
                for d in self.devices:
                    if d["adaptor_install"][0]["id"] == msg["id"]:
                        response = {
                        "cmd": "config",
                        "config": 
                            {"apps": d["adaptor_install"][0]["apps"], 
                             "name": d["adaptor_install"][0]["adaptor"]["name"],
                             "friendly_name": d["friendly_name"],
                             "btAddr": d["mac_addr"],
                             "btAdpt": "hci0", 
                             "sim": self.sim
                            }
                        }
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
                print ModuleName, "Sending config to conc:", response
                self.cbSendConcMsg(response)
            else:
                print ModuleName, "Config req from unknown instance: ", \
                    msg["id"]
                response = {"cmd": "error"}
                self.cbSendMsg(response, msg["id"])

if __name__ == '__main__':
    m = ManageBridge()
