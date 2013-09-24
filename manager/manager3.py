#!/usr/bin/env python
#manager2.py
ModuleName = "Bridge Manager      "

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
from autobahn.websocket import WebSocketClientFactory, \
                               WebSocketClientProtocol, \
                               connectWS

class ManageBridge:

    def __init__(self):
        """ apps and adts data structures will be stored in a local file.
            For now just create them here as static structures. """
        self.discovered = False
        self.reqSync = False
        self.stopping = False
        self.apps = {"app1": 
               {"name": "living",
                "exe": "/home/pi/bridge/apps/living.py",
                "mgrSoc": "/tmp/livingManagerSocket",
                "numAdtSocs": 1,
                "adtSocs": ["/tmp/tagAppSocket1"]}
           }
        self.adts = {"adt1": 
               {"name": "SensorTag",
                "method": "btle",
                "exe": "/home/pi/bridge/drivers/acceladaptor2.py",             
                "btAddr": "90:59:AF:04:2B:92",
                "mgrSoc": "/tmp/tag1ManagerSocket",
                "numAppSoc": 1,
                "appSocs": ["/tmp/tagAppSocket1"],
                "btAdpt": "hci0"}
            }
        
    def initBridge(self):
        print ModuleName, "Hello from the Bridge Manager"

    def listMgrSocs(self):
        mgrSocs ={} 
        for adaptor in self.adts:
            mgrSocs[adaptor] = self.adts[adaptor]["mgrSoc"]
        for app in self.apps:
            mgrSocs[app] = self.apps[app]["mgrSoc"]
        return mgrSocs

    def startAll(self):
        self.stopping = False
        # Start adaptors
        for adaptor in self.adts:
            try:
                exe = self.adts[adaptor]["exe"]
                btAddr = self.adts[adaptor]["btAddr"]
                btAdpt = self.adts[adaptor]["btAdpt"]
                mgrSoc = self.adts[adaptor]["mgrSoc"]
                appSoc = self.adts[adaptor]["appSocs"][0]
                subprocess.Popen([exe, btAdpt, btAddr, mgrSoc, appSoc])
                print ModuleName, self.adts[adaptor]["name"], " started"
                # Give time for adaptor to start before starting the next one
                time.sleep(2)
            except:
                print ModuleName, self.adts[adaptor]["name"], " failed to start"
                time.sleep(2)

        # Give time for all adaptors to start before starting apps
        time.sleep(5)
        for app in self.apps:
            try:
                exe = self.apps[app]["exe"]
                mgrSoc = self.apps[app]["mgrSoc"]
                adtSoc = self.apps[app]["adtSocs"][0]
                subprocess.Popen([exe, mgrSoc, adtSoc])
                print ModuleName, self.apps[app]["name"], " started"
            except:
                print ModuleName, self.apps[app]["name"], " failed to start"

    def doDiscover(self):
        exe = "/home/pi/bridge/manager/discovery.py"
        type = "btle"
        output = subprocess.check_output([exe, type])
        self.devices = json.loads(output)
        print ModuleName, "Devices: ", self.devices
        self.discovered = True

    def discover(self):
        d = threads.deferToThread(self.doDiscover)

    def processControlMsg(self, msg):
        if msg["cmd"] == "start":
            print ModuleName, "starting adaptors and apps"
            self.startAll()
        elif msg["cmd"] == "discover":
            self.discover()
        elif msg["cmd"] == "stopapps":
            self.stopApps()
        elif msg["cmd"] == "stopall":
            self.stopApps()
            reactor.callLater(8, self.stopManager)
        elif msg["cmd"] == "update":
            self.reqSync = True

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
        if self.stopping:
            response = {"cmd": "stop"}
        else:
            response = {"cmd": "ok"}
        return response

class BridgeControllerProtocol(WebSocketClientProtocol):

    def sendHello(self):
        msg = {"status": "ready"}
        self.sendMessage(json.dumps(msg))

    def onOpen(self):
        self.sendHello()
        self.monitorBridge()

    def onMessage(self, rawMsg, binary):
        msg = json.loads(rawMsg)
        m.processControlMsg(msg)

    def monitorBridge(self):
        if m.checkBridge():
            msg = m.getManagerMsg()
            self.sendMessage(json.dumps(msg))
        reactor.callLater(2, self.monitorBridge)

class ManagerSockets(LineReceiver):

    def lineReceived(self, data):
        #print ModuleName, "Received line: ", data
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
        print "Usage: manager <aggregator ip address>:<aggregator socket>"
        exit(1)
    aggregator = "ws://" + sys.argv[1]
    print ModuleName, "Aggregator = ", aggregator

    m = ManageBridge()
    m.initBridge()
    # WebSocket for communicating with bridge controller
    #wsfactory = WebSocketClientFactory("ws://192.168.0.15:9000", debug = False)
    wsfactory = WebSocketClientFactory(aggregator, debug = False)
    wsfactory.protocol = BridgeControllerProtocol
    connectWS(wsfactory)

    # Sockets for communicating with each adaptor and app
    mgrSocFactory=Factory()
    mgrSocFactory.protocol = ManagerSockets

    # Open sockets for communicating with all apps and adaptors
    mgrSocs = m.listMgrSocs()
    for item in mgrSocs:
        try:
            reactor.listenUNIX(mgrSocs[item], mgrSocFactory, backlog=4)
            print ModuleName, "Opened socket ", mgrSocs[item]
        except:
            print ModuleName, "Failed to open socket ", mgrSocs[item]

    reactor.run()
