#!/usr/bin/env python
# conduit.py
# Copyright (C) ContinuumBridge Limited, 2013-2016 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Mark Claydon/Peter Claydon
#
from twisted.internet import reactor
# Import cbclient from the parent directory
import os.path, sys
sys.path.append("../client-python")
from cbclient import CBClient
import json
from cbcommslib import CbClientProtocol
from cbcommslib import CbClientFactory
from cbconfig import *

class Conduit(CBClient):

    def onConnect(self, response):
        logging.info("MyBridgeClient Server connected: {0}".format(response.peer))
        self.factory.resetDelay()

    def onOpen(self):
        logging.info("WebSocket connection open")

        initMsg = {"status": "open"}
        self.concFactory = CbClientFactory(self.onConcentrator, initMsg)
        self.concConnect = reactor.connectUNIX("/tmp/cbridge/SKT-CONC-COND", self.concFactory, timeout=10)

    def onConcentrator(self, message):
        #logging.debug("onConcentrator, message" + str(message))
        if "status" in message:
            if message["status"] == "stop":
                self.destroySocket()
                reactor.stop()
        else:
            logging.debug("Conduit sending: {}".format(message))
            self.sendMessage(message["destination"], message["body"], source=message["source"])

    def onMessage(self, message, isBinary):
        logging.info("onMessage: " + str(message))
        self.concFactory.sendMsg(json.loads(message))

    def onClose(self, wasClean, code, reason):
        logging.info("WebSocket connection closed, reason: {}".format(reason))
        self.concFactory.sendMsg({"status": "closed"})

conduit = Conduit(is_bridge=True, reactor=reactor, key=CB_BRIDGE_KEY, logFile="/var/log/cbridge.log", logLevel=logging.DEBUG)

reactor.run()
