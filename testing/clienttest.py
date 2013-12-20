#!/usr/bin/env python
ModuleName = "Client              "

import sys
import os.path
import time
import json
from pprint import pprint
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import defer
from twisted.internet import reactor

class cbConcClient(LineReceiver):
    def connectionMade(self):
        print ModuleName, "cbConcClient connected to concentrator", self.id
        #req = {"id": self.id,
               #"req": "init"}
        req = self.req
        self.sendLine(json.dumps(req))

    def lineReceived(self, data):
        msg = json.loads(data)
        print ModuleName, self.id, " cbConcClient received from conc: ", msg 
        self.transport.loseConnection

    def sendReq(self, req):
        print ModuleName, "cbConcClient req = ", req
        self.sendLine(json.dumps(req))

class cbClientFactory(ReconnectingClientFactory):
    #def buildProtocol(self, addr):
        #print 'Connected - buildProtocol'
        #return cbConcClient()

    def testPrint(self, msg):
        print "testPrint", msg
        self.protocol.sendReq(msg)

    def clientReady(self, instance):
        self.clientInstance = instance
        print "clientReady Intance = ", self.clientInstance

    def clientConnectionFailed(self, connector, reason):
        print ModuleName, self.id, " failed to connect"
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        print ModuleName, self.id, " connection lost"
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

class App():
    def __init__(self):
        self.id = "AppID"
        self.concFactory = cbClientFactory()
        self.concFactory.id = self.id
        self.concFactory.protocol = cbConcClient
        self.concFactory.protocol.id = self.id
        #self.sendReq = self.concFactory.protocol.sendReq
        req = {"id": self.id,
               "req": "req from outside"}
        self.concFactory.protocol.req = req
        self.soc = reactor.connectUNIX("tmpSoc", self.concFactory, timeout=10)
        print "self.soc = ", self.soc
        reactor.callLater(1, self.process)
        print "starting reactor"
        reactor.run()

    def process(self):
        print "Starting to process"
        req = {"id": self.id,
               "req": "second req"}
        self.concFactory.protocol.req = req
        self.soc = reactor.connectUNIX("tmpSoc", self.concFactory, timeout=10)
        print "process sent message"

if __name__ == '__main__':

    app = App()

