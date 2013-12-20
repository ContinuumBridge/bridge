#!/usr/bin/env python
# concentrator.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
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

class cbAdaptorProtocol(LineReceiver):
    def lineReceived(self, data):
        print "Concentrator received", data
        resp = {"id": "conc",
                "data": "conc response"
               }
        self.sendResp(resp)

    def sendResp(self, resp):
        self.sendLine(json.dumps(resp))

class Concentrator():
    def __init__(self, argv):
        appConcSoc = "tmpSoc"
        id = "conc"
        self.cbFactory = Factory()
        self.cbFactory.protocol = cbAdaptorProtocol
        reactor.listenUNIX(appConcSoc, self.cbFactory)
        reactor.run()

if __name__ == '__main__':
    concentrator = Concentrator(sys.argv)
