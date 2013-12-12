#!/usr/bin/env python
# manager9.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Bridge Manager      "
id = "manager10"

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
        self.discovered = False
        self.configured = False
        self.reqSync = False
        self.stopping = False
        self.appProcs = []
        self.concConfig = []
        status = self.readConfig()
        print ModuleName, status
      
    def initBridge(self):
        print ModuleName, "Hello from the Bridge Manager"

    def listMgrSocs(self):
        mgrSocs =[] 
        for d in self.devices:
            mgrSocs.append(d["device"]["adaptor"]["mgrSoc"])
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
            exe = d["device"]["adaptor"]["exe"]
            fName = d["device"]["friendlyName"]
            id = d["device"]["id"]
            mgrSoc = d["device"]["adaptor"]["mgrSoc"]
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
        exe = "/home/pi/bridge/manager/discovery.py"
        #exe = "/home/petec/bridge/manager/testDiscovery.py"
        type = "btle"
        output = subprocess.check_output([exe, type])
        discOutput = json.loads(output)
        self.discoveredDevices["status"] = discOutput["status"]
        self.discoveredDevices["devices"] = []
        if self.configured:
            for d in discOutput["devices"]:
                addrFound = False
                if d["method"] == "btle":
                    for oldDev in self.devices:
                       if oldDev["device"]["method"] == "btle": 
                           if d["addr"] == oldDev["device"]["btAddr"]:
                               addrFound = True
                if addrFound == False:
                    self.discoveredDevices["devices"].append(d)  
        else:
            for d in discOutput["devices"]:
                self.discoveredDevices["devices"].append(d)  
        print ModuleName, "Discovered devices:"
        print ModuleName, self.discoveredDevices
        self.discovered = True

    def discover(self):
        d = threads.deferToThread(self.doDiscover)

    def readConfig(self):
        #self.bridgeRoot = "/home/petec/bridge/"
        self.bridgeRoot = "/home/pi/bridge/"
        self.appRoot = self.bridgeRoot + "apps/"
        self.adtRoot = self.bridgeRoot + "adaptors/"
        self.concPath = self.bridgeRoot + "concentrator/concentrator.py"
        try:
            with open('bridge.config', 'r') as configFile:
                config = json.load(configFile)
                self.bridgeID = config["bridge"]["id"]
                self.friendlyName = config["bridge"]["friendlyName"]
                self.apps = config["bridge"]["apps"]
                self.devices = config["bridge"]["devices"]
                self.configured = True
        except:
            print ModuleName, "Warning. No config file exists"
            self.configured = False

        if self.configured:
            # Process config to determine routing:
            for d in self.devices:
                d["device"]["id"] = "dev" + d["device"]["id"]
                socket = "mgr-" + d["device"]["id"]
                d["device"]["adaptor"]["mgrSoc"] = socket
                d["device"]["adaptor"]["exe"] = self.adtRoot + \
                    d["device"]["adaptor"]["exe"]
                # Add a apps list to each device adaptor
                d["device"]["adaptor"]["apps"] = []
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["app"]["id"] = "app" + a["app"]["id"]
                a["app"]["exe"] = self.appRoot + a["app"]["exe"]
                a["app"]["mgrSoc"] = "mgr-" + a["app"]["id"]
                a["app"]["concSoc"] = "conc-" + a["app"]["id"]
                for appDev in a["devices"]:
                    uri = appDev["resource_uri"]
                    for d in self.devices: 
                        if d["device"]["adaptor"]["resource_uri"] == uri:
                            socket = "skt-" \
                                + d["device"]["id"] + "-" + a["app"]["id"]
                            d["device"]["adaptor"]["apps"].append(
                                                    {"adtSoc": socket,
                                                     "name": a["app"]["name"],
                                                     "id": a["app"]["id"]
                                                    }) 
                            appDev["adtSoc"] = socket
                            appDev["id"] = d["device"]["id"]
                            appDev["name"] = d["device"]["adaptor"]["name"]
                            appDev["friendlyName"] = d["device"]["friendlyName"]
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
        if msg["cmd"] == "start":
            if self.configured:
                print ModuleName, "starting adaptors and apps"
                self.startAll()
            else:
                print ModuleName, "Can't start adaptors & apps"
                print ModuleName, "Please run discovery"
        elif msg["cmd"] == "discover":
            self.discover()
        elif msg["cmd"] == "stopapps":
            self.stopApps()
        elif msg["cmd"] == "stopall" or msg["cmd"] == "stop":
            if not self.stopping:
                print ModuleName, "Processing stop. Stopping apps"
                self.stopApps()
                reactor.callLater(10, self.stopManager)
            else:
                self.stopManager()
        elif msg["cmd"] == "update":
            self.reqSync = True
        elif msg["cmd"] == "config":
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
            for appDev in a["devices"]:
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
            msg = {"status": "reqSync"}
            self.reqSync = False
        else:
            msg = {"status": "ok"}
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
                                    "config": {"adts": a["devices"],
                                               "concentrator": conc}}
                        break
            elif msg["type"] == "adt": 
                for d in self.devices:
                    if d["device"]["id"] == msg["id"]:
                        response = {
                        "cmd": "config",
                        "config": {"apps": d["device"]["adaptor"]["apps"], 
                                   "name": d["device"]["name"],
                                   "friendlyName": d["device"]["friendlyName"],
                                   "btAddr": d["device"]["btAddr"],
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
        msg = {"id": id,
               "status": "ready"}
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
