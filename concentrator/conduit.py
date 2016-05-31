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

class Conduit(CBClient):

    def onConnect(self, response):
        self.logger.info("MyBridgeClient Server connected: {0}".format(response.peer))
        self.factory.resetDelay()

    def onOpen(self):
        self.logger.info("WebSocket connection open")

        initMsg = {"status": "open"}
        self.concFactory = CbClientFactory(self.onConcentrator, initMsg)
        self.concConnect = reactor.connectUNIX("/tmp/cbridge/SKT-CONC-COND", self.concFactory, timeout=10)

    def onConcentrator(self, message):
        #self.logger.debug("onConcentrator, message" + str(message))
        if "status" in message:
            if message["status"] == "stop":
                self.destroySocket()
                reactor.stop()
        else:
            self.sendMessage(message["destination"], message["body"])

    def onMessage(self, message, isBinary):
        self.logger.info("onMessage: " + str(message))
        self.concFactory.sendMsg(json.loads(message))

    def onClose(self, wasClean, code, reason):
        self.logger.info("WebSocket connection closed")
        self.concFactory.sendMsg({"status": "closed"})

conduit = Conduit(is_bridge=True, reactor=reactor, key=CB_BRIDGE_KEY)

reactor.run()
