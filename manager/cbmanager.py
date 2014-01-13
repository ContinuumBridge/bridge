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
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory

class ManageBridge:

    def __init__(self):
        """ apps and adts data structures are stored in a local file.
        """
        self.bridgeRoot = os.getenv('CB_BRIDGE_ROOT', "/home/bridge/bridge")
        print ModuleName, "CB_BRIDGE_ROOT = ", self.bridgeRoot
        self.noCloud = os.getenv('CB_NO_CLOUD', "False")
        print ModuleName, "CB_NO_CLOUD = ", self.noCloud
        self.controllerAddr = os.getenv('CB_CONTROLLER_ADDR', '54.194.28.63')
        print ModuleName, "CB_CONTROLLER_ADDR = ", self.controllerAddr
        self.email = "cde5fb1645e74314a3e6841a4df0828d@continuumbridge.com"
        self.password = "zqN17m94GftDvNiWNGls+6tyxryCJFWxzWC5hs/fTmF7YXn4i8eogVa/HzwK5fK2"
        self.discovered = False
        self.configured = False
        self.reqSync = False
        self.stopping = False
        self.concNoApps = False
        self.appProcs = []
        self.concConfig = []
        self.cbFactory = {} 
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
        s = "mgr-conc"
        try:
            self.cbConcFactory = CbServerFactory(self.processClient)
            reactor.listenUNIX(s, self.cbConcFactory, backlog=4)
            print ModuleName, "Opened manager socket ", s
        except:
            print ModuleName, "Socket already exits: ", s

        # Now start the concentrator in a subprocess
        exe = self.concPath
        id = "conc"
        mgrSoc = "mgr-conc"
        try:
            self.concProc = subprocess.Popen([exe, mgrSoc, id])
            print ModuleName, "Started concentrator"
        except:
            print ModuleName, "Concentrator failed to start"
            print ModuleName, "Params: ", exe, id, mgrSoc

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
                reactor.listenUNIX(mgrSocs[s], self.cbFactory[s], backlog=4)
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
        time.sleep(5)
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
 
    def doDiscover(self):
        self.discoveredDevices = {}
        exe = self.bridgeRoot + "/manager/discovery.py"
        type = "btle"
        output = subprocess.check_output([exe, type])
        discOutput = json.loads(output)
        self.discoveredDevices["msg"] = "req"
        self.discoveredDevices["req"] = "post"
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
        self.cbSendConcMsg(msg)
        self.discovered = True

    def discover(self):
        d = threads.deferToThread(self.doDiscover)

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
                socket = "mgr-" + str(d["adaptor_install"][0]["id"])
                d["adaptor_install"][0]["mgrSoc"] = socket
                d["adaptor_install"][0]["adaptor"]["exe"] = adtRoot + \
                    d["adaptor_install"][0]["adaptor"]["exe"]
                # Add a apps list to each device adaptor
                d["adaptor_install"][0]["apps"] = []
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["app"]["id"] = "app" + str(a["app"]["id"])
                a["app"]["exe"] = appRoot + a["app"]["exe"]
                a["app"]["mgrSoc"] = "mgr-" + str(a["app"]["id"])
                a["app"]["concSoc"] = "conc-" + str(a["app"]["id"])
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
            elif msg["body"] == "discover":
                self.discover()
            elif msg["body"] == "stopapps":
                if not self.stopping:
                    self.stopApps()
            elif msg["body"] == "stopall" or msg["body"] == "stop":
                if not self.stopping:
                    print ModuleName, "Processing stop. Stopping apps"
                    self.stopApps()
                    reactor.callLater(10, self.stopAll)
                else:
                    self.stopAll()
            elif msg["body"] == "update_config":
                req = {"cmd": "msg",
                       "msg": {"msg": "req",
                               "req": "get",
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

    def stopAll(self):
        """ Kills concentrator & nodejs processes, removes sockets & kills itself """
        print ModuleName, "Stopping concentrator"
        msg = {"cmd": "stop"}
        self.cbSendConcMsg(msg)
        # Give concentrator a change to stop before killing it and its sockets
        reactor.callLater(1, self.stopManager)

    def stopManager(self):
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
        reactor.stop()
        sys.exit

    def stopApps(self):
        """ Asks apps & adaptors to clean up nicely and die. """
        print ModuleName, "Stopping apps and adaptors"
        self.stopping = True
        mgrSocs = self.listMgrSocs()
        for a in mgrSocs:
            msg = {"cmd": "stop"}
            self.cbSendMsg(msg, a)
        reactor.callLater(8, self.killAppProcs)

    def killAppProcs(self):
        """ In case apps & adaptors have not shut down, kill their processes. """
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
                       "body": "apps_stopped"
                      }
              }
        self.cbSendConcMsg(msg)
 
    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def cbSendConcMsg(self, msg):
        self.cbConcFactory.sendMsg(msg)

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
                             "btAdpt": "hci0" 
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
