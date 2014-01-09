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
        self.discovered = False
        self.configured = False
        self.reqSync = False
        self.stopping = False
        self.appProcs = []
        self.concConfig = []
        self.mgrSocFactory = {} 
        status = self.readConfig()
        print ModuleName, status

        # Manager socket factory for connecting to conc, apps  adaptors
        self.initBridge()
        reactor.run()

    def initBridge(self):
        if self.noCloud != "True":
            print ModuleName, "Bridge Manager Starting JS Concentrator"
            exe = "nodejs"
            path = self.bridgeRoot + "/nodejs/index.js"
            try:
                p = subprocess.Popen([exe, path])
                print ModuleName, "Started node.js"
            except:
                print ModuleName, "node.js failed to start. exe = ", exe
            # Give time for node interface to start
        else:
            print ModuleName, "Running without Cloud Server"
        time.sleep(2)

        self.startConcentrator()
        if self.configured:
            self.startAll()

    def listMgrSocs(self):
        mgrSocs = {}
        for d in self.devices:
            mgrSocs[d["adaptor_install"][0]["id"]] = d["adaptor_install"][0]["mgrSoc"]
        for a in self.apps:
            mgrSocs[a["app"]["id"]] = a["app"]["mgrSoc"]
        #mgrSocs.append("mgr-conc")
        return mgrSocs

    def startConcentrator(self):
        # Open a socket for communicating with the concentrator
        s = "mgr-conc"
        try:
            self.mgrSocFactory["conc"] = CbServerFactory(self.processClient)
            reactor.listenUNIX(s, self.mgrSocFactory["conc"], backlog=4)
            print ModuleName, "Opened manager socket ", s
        except:
            print ModuleName, "Manager socket already exits: ", s

        # Now start the concentrator in a subprocess
        exe = self.concPath
        id = "conc"
        mgrSoc = "mgr-conc"
        try:
            p = subprocess.Popen([exe, mgrSoc, id])
            self.appProcs.append(p)
            print ModuleName, "Started concentrator"
        except:
            print ModuleName, "Concentrator failed to start"
            print ModuleName, "Params: ", exe, id, mgrSoc
        # Give time for concentrator to start
        #time.sleep(2)

    def startAll(self):
        self.stopping = False
        # Open sockets for communicating with all apps and adaptors
        mgrSocs = self.listMgrSocs()
        for s in mgrSocs:
            try:
                self.mgrSocFactory[s] = CbServerFactory(self.processClient)
                reactor.listenUNIX(mgrSoc[s], self.mgrSocFactory, backlog=4)
                print ModuleName, "Opened manager socket ", s
            except:
                print ModuleName, "Manager socket already exits: ", s

        # Start concentrator 
        # Start adaptors
        for d in self.devices:
            exe = d["adaptor_install"][0]["adaptor"]["exe"]
            fName = d["adaptor_install"][0]["friendlyName"]
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
        self.discoveredDevices["req"] = "discovered"
        self.discoveredDevices["data"] = []
        if self.configured:
            for d in discOutput["data"]:
                addrFound = False
                if d["method"] == "btle":
                    for oldDev in self.devices:
                       if oldDev["adaptor_install"][0]["adaptor"]["method"] == "btle": 
                           if d["addr"] == oldDev["mac_addr"]:
                               addrFound = True
                if addrFound == False:
                    self.discoveredDevices["data"].append(d)  
        else:
            for d in discOutput["data"]:
                self.discoveredDevices["data"].append(d)  
        print ModuleName, "Discovered devices:"
        print ModuleName, self.discoveredDevices
        self.discovered = True

    def discover(self):
        d = threads.deferToThread(self.doDiscover)

    def readConfig(self):
        appRoot = self.bridgeRoot + "/apps/"
        adtRoot = self.bridgeRoot + "/adaptors/"
        self.concPath = self.bridgeRoot + "/concentrator/concentrator.py"
        try:
            with open('bridge.config', 'r') as configFile:
                config = json.load(configFile)
                self.bridgeID = config["data"]["id"]
                self.friendlyName = config["data"]["friendlyName"]
                self.apps = config["data"]["apps"]
                self.devices = config["data"]["devices"]
                self.configured = True
        except:
            print ModuleName, "Warning. No config file exists"
            self.configured = False

        if self.configured:
            # Process config to determine routing:
            for d in self.devices:
                d["adaptor_install"][0]["id"] = "dev" + d["adaptor_install"][0]["id"]
                socket = "mgr-" + d["adaptor_install"][0]["id"]
                d["adaptor_install"][0]["mgrSoc"] = socket
                d["adaptor_install"][0]["adaptor"]["exe"] = adtRoot + \
                    d["adaptor_install"][0]["adaptor"]["exe"]
                # Add a apps list to each device adaptor
                d["adaptor_install"][0]["apps"] = []
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["app"]["id"] = "app" + a["app"]["id"]
                a["app"]["exe"] = appRoot + a["app"]["exe"]
                a["app"]["mgrSoc"] = "mgr-" + a["app"]["id"]
                a["app"]["concSoc"] = "conc-" + a["app"]["id"]
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
                            appDev["friendlyName"] = \
                                d["adaptor_install"][0]["friendlyName"]
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
            if msg["data"] == "start":
                if self.configured:
                    print ModuleName, "starting adaptors and apps"
                    self.startAll()
                else:
                    print ModuleName, "Can't start adaptors & apps"
                    print ModuleName, "Please run discovery"
            elif msg["data"] == "discover":
                self.discover()
            elif msg["data"] == "stopapps":
                self.stopApps()
            elif msg["data"] == "stopall" or msg["data"] == "stop":
                if not self.stopping:
                    print ModuleName, "Processing stop. Stopping apps"
                    self.stopApps()
                    reactor.callLater(10, self.stopManager)
                else:
                    self.stopManager()
            elif msg["data"] == "update":
                self.reqSync = True
        elif msg["msg"] == "resp":
            self.updateConfig(msg)

    def stopManager(self):
        print ModuleName, "Stopping manager"
        reactor.stop()
        #time.sleep(1)
        #self.delManagerSockets()
        sys.exit

    def stopApps(self):
        print ModuleName, "Stopping apps and adaptors"
        self.stopping = True
        reactor.callLater(9, self.killAppProcs)

    def killAppProcs(self):
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
        for soc in self.concConfig:
                socket = soc["appConcSoc"]
                try:
                    os.remove(socket) 
                    print ModuleName, socket, " removed"
                except:
                    print ModuleName, socket, " already removed"
 
    def delManagerSockets(self):
        mgrSocs = self.listMgrSocs()
        for s in mgrSocs:
            try:
                os.remove(s)
                print ModuleName, "Removed manager socket ", s
            except:
                print ModuleName, "Unable to remove manager socket: ", s

    def checkBridge(self):
        return True

    def getManagerMsg(self):
        if self.discovered:
            msg = self.discoveredDevices
            self.discovered = False
        elif self.reqSync:
            msg = {"msg": "req",
                   "req": "get",
                   "uri": "/api/v1/current_bridge/bridge"}
            self.reqSync = False
        else:
            msg = {"msg": "status",
                   "data": "ok"}
        return msg

    def processClient(self, msg):
        print ModuleName, "Received msg from client", msg
        response = {"cmd": "error"}
        if self.stopping:
            response = {"cmd": "stop"}
        elif msg["status"] == "req-config":
            if msg["type"] == "app":
                for a in self.apps:
                    if a["app"]["id"] == msg["id"]:
                        for c in self.concConfig:
                            if c["id"] == msg["id"]:
                                conc = c["appConcSoc"]
                                break
                        response = {"cmd": "config",
                                    "config": {"adts": a["device_permissions"],
                                               "concentrator": conc}}
                        break
            elif msg["type"] == "adt": 
                for d in self.devices:
                    if d["adaptor_install"][0]["id"] == msg["id"]:
                        response = {
                        "cmd": "config",
                        "config": 
                            {"apps": d["adaptor_install"][0]["apps"], 
                             "name": d["adaptor_install"][0]["name"],
                             "friendlyName": d["adaptor_install"][0]["friendlyName"],
                             "btAddr": d["adaptor_install"][0]["btAddr"],
                             "btAdpt": "hci0" 
                            }
                        }
                        break
            elif msg["type"] == "conc":
                self.concConfig = []
                for a in self.apps:
                    self.concConfig.append({"id": a["app"]["id"],
                                       "appConcSoc": a["app"]["concSoc"]})
                response = {"cmd": "config",
                            "config": self.concConfig 
                           }
            else:
                print ModuleName, "Config req from unknown instance: ", \
                    msg["id"]
                response = {"cmd": "error"}
        else:
            response = {"cmd": "ok"}
        return response

if __name__ == '__main__':
    m = ManageBridge()
