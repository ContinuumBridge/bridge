#!/usr/bin/env python
# concentrator.py
# Copyright (C) ContinuumBridge Limited, 2013-2016 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Mark Claydon/Peter Claydon
#
from twisted.internet import reactor
# Import cbclient from the parent directory
import os.path, sys
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))
from cbclient import CBClient
import json
from cbcommslib import CbClientProtocol
from cbcommslib import CbClientFactory
from cbconfig import *

class MyBridgeClient(CBClient):

    def onConnect(self, response):
        self.logger.info("MyBridgeClient Server connected: {0}".format(response.peer))
        self.factory.resetDelay()

    def onOpen(self):
        self.logger.info("WebSocket connection open.")

        initMsg = {"init": "OK"}
        self.concFactory = CbClientFactory(self.onConcentrator, initMsg)
        self.concConnect = reactor.connectUNIX("/tmp/cbridge/SKT-CONC-COND", self.concFactory, timeout=10)

    def onConcentrator(self, message):
        self.logger.debug("onConcentrator, message" + str(message))
        self.sendMessage(message["destination"], message["body"])

    def onMessage(self, message, isBinary):
        self.logger.info("onMessage: " + str(message))
        self.concFactory.sendMsg(json.loads(message))

    def onClose(self, wasClean, code, reason):
        print "CBClientProtocol onClose"

def goForIt():
    destination = "cb",
    body = {
        "verb": "patch",
        "resource": "/api/bridge/v1/bridge/106/",
        "body": {
        "status": "running"
        }
    }
    client.sendMessage(destination, body)
    #client.sendMessage("CID52", {"key": "value"})
    reactor.callLater(4, goForIt)

#format = "%(asctime)s %(levelname)s: %(name)s %(message)s"
#logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format=format)
#logger = logging.getLogger('CBClient')

client = MyBridgeClient(is_bridge=True, reactor=reactor)
#reactor.callLater(10, goForIt)

reactor.run()
