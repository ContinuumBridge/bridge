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
        self.reqSync = False
        self.stopping = False
        try:
            with open('bridge.config', 'r') as configFile:
                 config = json.load(configFile)
                 self.bridgeID = config["bridge"]["id"]
                 self.friendlyName = config["bridge"]["friendly"]
                 self.apps = config["bridge"]["apps"]
                 print ModuleName, "Config read from local file:"
                 print ModuleName, "Apps:"
                 pprint(self.apps)
                 self.adts = config["bridge"]["adpt"]
                 print ModuleName, "Adaptors:"
                 pprint(self.adts)
                 self.configured = True
        except:
            print ModuleName, "Warning. No config file exists"
            self.configured = False
       
    def initBridge(self):
        print ModuleName, "Hello from the Bridge Manager"

    def listMgrSocs(self):
        mgrSocs =[] 
        for a in self.adts:
            mgrSocs.append(a["mgrSoc"])
        for a in self.apps:
            mgrSocs.append(a["mgrSoc"])
        return mgrSocs

    def startAll(self):
        self.stopping = False
        # Open sockets for communicating with all apps and adaptors
        mgrSocs = self.listMgrSocs()
        for item in mgrSocs:
            try:
                reactor.listenUNIX(item, mgrSocFactory, backlog=4)
                print ModuleName, "Opened manager socket ", item
            except:
                print ModuleName, "Manager socket probably already open: ", \
                                    item

        # Start adaptors
        for a in self.adts:
            try:
                exe = a["exe"]
                id = a["id"]
                mgrSoc = a["mgrSoc"]
                subprocess.Popen([exe, mgrSoc, id])
                print ModuleName, id, " started"
                # Give time for adaptor to start before starting the next one
                time.sleep(2)
            except:
                print ModuleName, id, " failed to start"
                print ModuleName, "Tag params: ", exe, id, mgrSoc
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
        exe = "/home/pi/bridge/manager/discovery.py"
        type = "btle"
        output = subprocess.check_output([exe, type])
        self.devices = json.loads(output)
        self.discovered = True

    def discover(self):
        d = threads.deferToThread(self.doDiscover)

    def updateConfig(self, msg):
        with open('bridge.config', 'w') as configFile:
            json.dump(msg, configFile)
        self.bridgeID = msg["bridge"]["id"]
        self.friendlyName = msg["bridge"]["friendly"]
        self.apps = msg["bridge"]["apps"]
        self.adts = msg["bridge"]["adpt"]
        print ModuleName, "Received new config:"
        print ModuleName, "Bridge id: ", self.bridgeID
        print ModuleName, "Bridge name: ", self.friendlyName
        print ModuleName, "Apps:"
        pprint(self.apps)
        print ModuleName, "Adaptors:"
        pprint(self.adts)
        self.configured = True

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
        elif msg["cmd"] == "stopall" or msg["cmd"] == "stop":
            self.stopApps()
            reactor.callLater(5, self.stopManager)
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

    def checkBridge(self):
        return True

    def getManagerMsg(self):
        if self.discovered:
            msg = self.devices
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
                                    "config": {"adts": a["adts"]}}
            elif msg["class"] == "adt": 
                for a in self.adts:
                    if a["id"] == msg["id"]:
                        response = {
                        "cmd": "config",
                        "config": {"apps": a["apps"], 
                                   "name": a["name"],
                                   "btAddr": a["btAddr"],
                                   "btAdpt": a["btAdpt"]
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
