#!/usr/bin/env python
ModuleName = "Client              "

import sys
import os.path
import time
import json
from pprint import pprint
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import defer
from twisted.internet import reactor

class CbClient(LineReceiver):
    def __init__(self, processMsg, initMsg):
        self.processMsg = processMsg
        self.initMsg = initMsg

    def connectionMade(self):
        self.sendLine(json.dumps(self.initMsg))

    def lineReceived(self, data):
        msg = json.loads(data)
        self.processMsg(msg)

    def sendMsg(self, msg):
        self.sendLine(json.dumps(msg))

class CbClientFactory(ClientFactory):
    def __init__(self, processMsg, initMsg):
        self.processMsg = processMsg
        self.initMsg = initMsg

    def buildProtocol(self, addr):
        self.proto = CbClient(self.processMsg, self.initMsg)
        return self.proto

    def sendMsg(self, msg):
        self.proto.sendMsg(msg)

class App():
    def __init__(self):
        initMsg = {"id": "client connected"} 
        self.msgFactory = CbClientFactory(self.processMsg, initMsg)
        reactor.connectUNIX("tmpSoc", self.msgFactory, timeout=1)
        reactor.callLater(3, self.process)
        print ModuleName, "starting reactor"
        reactor.run()

    def processMsg(self, msg):
        print ModuleName, "Client received: ", msg

    def process(self):
        print ModuleName, "Starting to process"
        msg = {"id": "client message 2"}
        self.msgFactory.sendMsg(msg)
        print ModuleName, "process sent message"

if __name__ == '__main__':

    app = App()

