#!/usr/bin/env python
# concentrator.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Server              "

import sys
import time
import os
import json
from pprint import pprint
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import defer
from twisted.internet import reactor

class CbServerProtocol(LineReceiver):
    def __init__(self, processMsg):
        self.processMsg = processMsg

    def lineReceived(self, data):
        msg = json.loads(data)
        self.processMsg(msg)

    def sendMsg(self, msg):
        self.sendLine(json.dumps(msg))

class CbServerFactory(Factory):
    def __init__(self, processMsg):
        self.processMsg = processMsg

    def buildProtocol(self, addr):
        self.proto = CbServerProtocol(self.processMsg)
        return self.proto

    def sendMsg(self, msg):
        self.proto.sendMsg(msg) 

class Adaptor():
    def __init__(self):
        self.cbFactory = CbServerFactory(self.processMsg)
        reactor.listenUNIX("tmpSoc", self.cbFactory)
        reactor.run()

    def processMsg(self, msg):
        print ModuleName, "Server processing: ", msg  
        msg = {"id": "server response 1"}
        self.cbFactory.sendMsg(msg)
        msg = {"id": "server response 2"}
        self.cbFactory.sendMsg(msg)

if __name__ == '__main__':
    adaptor = Adaptor()
