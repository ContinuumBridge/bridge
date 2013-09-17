#!/usr/bin/env python
#manager2.py
ModuleName = "Bridge Manager      "

import sys
import time
import os
import subprocess
import json
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor, defer
from autobahn.websocket import WebSocketClientFactory, \
                               WebSocketClientProtocol, \
                               connectWS

def callback_func(result):
    print result

class ManageBridge:

    def __init__(self):
        """ apps and adts data structures will be stored in a local file.
            For now just create them here as static structures. """
        self.apps = {"app1": 
               {"name": "accelapp",
                "exe": "/home/pi/bridge/apps/accelapp2.py",
                "mgrSoc": "/tmp/accelManagerSocket",
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

class BridgeControllerProtocol(WebSocketClientProtocol):

    def sendHello(self):
        msg = {}
        msg["status"] = "ready"
        self.sendMessage(json.dumps(msg))

    def onOpen(self):
        self.sendHello()

    def onMessage(self, rawMsg, binary):
        print ModuleName, "Received message from Bridge Controller: " + rawMsg
        msg = json.loads(rawMsg)
        if msg["cmd"] == "start":
            print ModuleName, "starting adaptors and apps"
            m.startAll()

class ManagerSockets(Protocol):
    def dataReceived(self, data):
        #response = m.processReq(json.loads(data))
        #line = json.dumps(str(m.getAccel(gatttool))) + "\r\n" 
        #self.transport.write(json.dumps(response) + "\r\n")
        print ModuleName, "Received data on socket"
    def connectionMade(self):
        print Modulename, "Connection made to ", self.transport.getPeer()
    def connectionLost(self, reason):
        print ModuleName, "Disconnected"

if __name__ == '__main__':

    m = ManageBridge()
    m.initBridge()
    # WebSocket for communicating with bridge controller
    wsfactory = WebSocketClientFactory("ws://192.168.0.15:9000", debug = False)
    wsfactory.protocol = BridgeControllerProtocol
    connectWS(wsfactory)

    # Sockets for communicating with each adaptor and app
    mgrSocFactory=Factory()
    mgrSocFactory.protocol = ManagerSockets
    mgrSocs = m.listMgrSocs()
    for item in mgrSocs:
        try:
            reactor.listenUNIX(mgrSocs[item], mgrSocFactory, backlog=4)
            print ModuleName, "Opened socket ", mgrSocs[item]
        except:
            print ModuleName, "Failed to open socket ", mgrSocs[item]

    #d = defer.Deferred()
    #reactor.callLater(10, d.callback, "Manager has finished its job")
    #d.addCallback(callback_func)
    reactor.run()


