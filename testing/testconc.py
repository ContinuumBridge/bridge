#!/usr/bin/env python
# concentrator.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Concentrator        "

import sys
import time
import os
import json
from pprint import pprint
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ClientFactory
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import defer
from twisted.internet import reactor
from twisted.application.internet import TCPServer

class Concentrator():
    def __init__(self, argv):
        print ModuleName, "Hello"

        # Connection to websockets process
        initMsg = {"msg": "status",
                   "body": "ready"}
        self.concFactory = CbClientFactory(self.processServerMsg, initMsg)
        self.jsConnect = reactor.connectTCP("localhost", 5000, self.concFactory, timeout=10)
        print ModuleName, "Connecting to node on port 5000"
        reactor.callLater(10, self.sendNodeMsg)
        reactor.callLater(30, self.stopAll)
        reactor.run()

    def processServerMsg(self, msg):
        print ModuleName, "Received from controller: ", msg

    def sendNodeMsg(self):
        req = {"cmd": "msg",
               "msg": {"msg": "req",
                       "channel": "bridge_manager",
                       "req": "get",
                       "uri": "/api/v1/current_bridge/bridge"}
              }
        self.concFactory.sendMsg(req)

    def stopAll(self):
        print ModuleName, "Stopping reactor"
        reactor.stop()

class CbClientProtocol(LineReceiver):
    def __init__(self, processMsg, initMsg):
        self.processMsg = processMsg
        self.initMsg = initMsg

    def connectionMade(self):
        print "Connected to node"
        self.sendLine(json.dumps(self.initMsg))

    def lineReceived(self, data):
        print "Message received"
        self.processMsg(json.loads(data))

    def sendMsg(self, msg):
        self.sendLine(json.dumps(msg))

class CbClientFactory(ReconnectingClientFactory):
    def __init__(self, processMsg, initMsg):
        self.processMsg = processMsg
        self.initMsg = initMsg

    def buildProtocol(self, addr):
        self.proto = CbClientProtocol(self.processMsg, self.initMsg)
        return self.proto

    def sendMsg(self, msg):
        self.proto.sendMsg(msg)

    def clientConnectionFailed(self, connector, reason):
        print "Client connection failed: ", reason

    def clientConnectionLost(self, connector, reason):
        print "Client connection lost: ", reason

    def startedConnecting(self, connector): 
        print "Started connecting"

if __name__ == '__main__':
    concentrator = Concentrator(sys.argv)
