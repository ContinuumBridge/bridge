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

class ManageBridge:

    def __init__(self):
        """ apps and adts data structures are stored in a local file.
        """
        self.bridgeRoot = os.getenv('CB_BRIDGE_ROOT', "/home/bridge/bridge")
        print ModuleName, "CB_BRIDGE_ROOT = ", self.bridgeRoot
        self.discovered = False
        self.configured = False
        self.reqSync = False
        self.stopping = False
        self.appProcs = []
        self.concConfig = []
        #status = self.readConfig()
        #print ModuleName, status
      
    def initBridge(self):
        print ModuleName, "Hello from the Bridge Manager"

    def listMgrSocs(self):
        mgrSocs =[] 
        for d in self.devices:
            mgrSocs.append(d["adaptor_install"][0]["mgrSoc"])
        for a in self.apps:
            mgrSocs.append(a["app"]["mgrSoc"])
        mgrSocs.append("mgr-conc")
        return mgrSocs

    def startAll(self):
        self.stopping = False
        # Open sockets for communicating with all apps and adaptors
        mgrSocs = self.listMgrSocs()
        for s in mgrSocs:
            try:
                reactor.listenUNIX(s, mgrSocFactory, backlog=4)
                print ModuleName, "Opened manager socket ", s
            except:
                print ModuleName, "Manager socket already exits: ", s

        # Start concentrator 
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
        time.sleep(2)

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
        self.discoveredDevices["req"] = "discovered"
        self.discoveredDevices["data"] = []
        if self.configured:
            for d in discOutput["data"]:
                addrFound = False
                if d["method"] == "btle":
                    for oldDev in self.devices:
                       if oldDev["data"]["method"] == "btle": 
                           if d["addr"] == oldDev["data"]["btAddr"]:
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
        #try:
        with open('bridge.config', 'r') as configFile:
            config = json.load(configFile)
            print ModuleName, "readConfig"
            pprint(config)
            self.bridgeID = config["body"]["id"]
            self.apps = config["body"]["apps"]
            self.devices = config["body"]["devices"]
            self.configured = True
        #except:
            #print ModuleName, "Warning. No config file exists"
            #self.configured = False

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
                                d["adaptor_install"][0]["friendly_name"]
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
                self.stopApps()
            elif msg["body"] == "stopall" or msg["body"] == "stop":
                if not self.stopping:
                    print ModuleName, "Processing stop. Stopping apps"
                    self.stopApps()
                    reactor.callLater(10, self.stopManager)
                else:
                    self.stopManager()
            elif msg["body"] == "update_config":
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
        #print ModuleName, "Recevied msg from client", msg
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
                             "friendlyName": d["adaptor_install"][0]["friendly_name"],
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

class ConcProtocol(LineReceiver):
    def connectionMade(self):
        msg = {"msg": "status",
               "data": "ready"}
        self.sendLine(json.dumps(msg))
        reactor.callLater(2, self.monitorBridge)

    def lineReceived(self, line):
        print ModuleName, line
        managerMsg = json.loads(line)
        msg = json.loads(line)
        m.processControlMsg(msg)

    def monitorBridge(self):
        if m.checkBridge():
            msg = m.getManagerMsg()
            self.sendLine(json.dumps(msg))
        reactor.callLater(2, self.monitorBridge)

class ConcFactory(ReconnectingClientFactory):
    """ Tries to reconnect to socket if connection lost """
    def clientConnectionFailed(self, connector, reason):
        print ModuleName, "Failed to connect to concentrator"
        print ModuleName,  reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        print ModuleName, "Connection to concentrator lost"
        print ModuleName, reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

class ManagerSockets(LineReceiver):

    def lineReceived(self, data):
        if data != "":
            response = m.processClient(json.loads(data))
        else:
            response = {"cmd": "blank message"}
        self.sendLine(json.dumps(response))

    def connectionMade(self):
        print ModuleName, "Connection made to ", self.transport.getPeer()

    def connectionLost(self, reason):
        print ModuleName, "Disconnected"

if __name__ == '__main__':

    if len(sys.argv) < 2:
        print "Usage: manager <concentrator socket address>"
        exit(1)
    concSocket = sys.argv[1]
    print ModuleName, "Concentrator = ", concSocket

    m = ManageBridge()
    m.initBridge()

    concFactory = ConcFactory()
    concFactory.protocol = ConcProtocol
    reactor.connectTCP("localhost", int(concSocket), concFactory, timeout=10)

    # Sockets factory for communicating with each adaptor and app
    mgrSocFactory=Factory()
    mgrSocFactory.protocol = ManagerSockets

    reactor.run()
