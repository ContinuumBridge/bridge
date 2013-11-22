#!/usr/bin/env python
#manager7.py
ModuleName = "Bridge Manager      "
id = "manager7"

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
        status = self.readConfig()
        print ModuleName, status
      
    def initBridge(self):
        print ModuleName, "Hello from the Bridge Manager"

    def listMgrSocs(self):
        mgrSocs =[] 
        for d in self.devices:
            mgrSocs.append(d["adt"]["mgrSoc"])
        for a in self.apps:
            mgrSocs.append(a["mgrSoc"])
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

        # Start adaptors
        for d in self.devices:
            exe = d["adt"]["exe"]
            fName = d["friendlyName"]
            id = d["id"]
            mgrSoc = d["adt"]["mgrSoc"]
            try:
               subprocess.Popen([exe, mgrSoc, id])
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
                id = a["id"]
                exe = a["exe"]
                mgrSoc = a["mgrSoc"]
                subprocess.Popen([exe, mgrSoc, id])
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
                       if oldDev["method"] == "btle": 
                           if d["addr"] == oldDev["btAddr"]:
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
        self.adtRoot = self.bridgeRoot + "drivers/"
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
            #try:
            # Process config to determine routing:
            for d in self.devices:
                socket = "mgr-" + d["id"]
                d["adt"]["mgrSoc"] = socket
                d["adt"]["exe"] = self.adtRoot + d["adt"]["exe"]
                # Add a apps list to each device adaptor
                d["adt"]["apps"] = []
            # Add socket descriptors to apps and devices
            for a in self.apps:
                a["exe"] = self.appRoot + a["exe"]
                a["mgrSoc"] = "mgr-" + a["id"]
                for appDev in a["devices"]:
                    uri = appDev["resource_uri"]
                    for d in self.devices: 
                        if d["adt"]["resource_uri"] == uri:
                            socket = "skt-" \
                                + d["id"] + "-" + a["id"]
                            d["adt"]["apps"].append({"adtSoc": socket,
                                                     "name": a["name"],
                                                     "id": a["id"]
                                                   }) 
                            appDev["adtSoc"] = socket
                            appDev["id"] = d["id"]
                            appDev["name"] = d["adt"]["name"]
                            appDev["friendlyName"] = d["friendlyName"]
                            appDev["adtSoc"] = socket
                            break
            #except:
                #print ModuleName, "Error processing configuration"
                #self.configured = False
        if self.configured:
            print ModuleName, "Config information processed:"
            print ModuleName, "Apps:"
            pprint(self.apps)
            print ""
            print ModuleName, "Devices:"
            pprint(self.devices)
            print ""
    
    def updateConfig(self, msg):
        with open('bridge.config', 'w') as configFile:
            json.dump(msg, configFile)
        status = self.readConfig()
        print ModuleName, status

    def processControlMsg(self, msg):
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
            reactor.callLater(5, self.delManagerSockets)
        elif msg["cmd"] == "stopall" or msg["cmd"] == "stop":
            self.stopApps()
            reactor.callLater(5, self.delManagerSockets)
            reactor.callLater(1, self.stopManager)
        elif msg["cmd"] == "update":
            self.reqSync = True
        elif msg["cmd"] == "config":
            self.updateConfig(msg)

    def stopManager(self):
        print ModuleName, "Stopping manager"
        reactor.stop()
        sys.exit

    def stopApps(self):
        print ModuleName, "Stopping apps and adaptors"
        self.stopping = True

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
            if msg["class"] == "app":
                for a in self.apps:
                    if a["id"] == msg["id"]:
                        response = {"cmd": "config",
                                    "config": {"adts": a["devices"]}}
                        break
            elif msg["class"] == "adt": 
                for d in self.devices:
                    if d["id"] == msg["id"]:
                        response = {
                        "cmd": "config",
                        "config": {"apps": d["adt"]["apps"], 
                                   "name": d["name"],
                                   "btAddr": d["btAddr"],
                                   "btAdpt": "hci0" 
                                  }
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
