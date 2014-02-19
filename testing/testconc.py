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
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import defer
from twisted.internet import reactor
from twisted.application.internet import TCPServer
from twisted.application.service import Application
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet.task import deferLater
from twisted.web.server import NOT_DONE_YET
from cbcommslib import CbClientProtocol
from cbcommslib import CbClientFactory
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory

class Concentrator():
    def __init__(self, argv):
        print ModuleName, "Hello"

        # Connection to websockets process
        initMsg = {"msg": "status",
                   "body": "ready"}
        self.concFactory = CbClientFactory(self.processServerMsg, initMsg)
        self.jsConnect = reactor.connectTCP("localhost", 5001, self.concFactory, timeout=10)
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

if __name__ == '__main__':
    concentrator = Concentrator(sys.argv)
