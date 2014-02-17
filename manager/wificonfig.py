#!/usr/bin/env python
# wificonfig.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "WiFiConfig          "

import sys
import time
import os
import json
from pprint import pprint
from twisted.internet import reactor
from twisted.application.internet import TCPServer
from twisted.application.service import Application
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet.task import deferLater
from twisted.web.server import NOT_DONE_YET

class RootResource(Resource):
    isLeaf = True
    def __init__(self, bridgeRoot):
        self.bridgeRoot = bridgeRoot
        Resource.__init__(self)

    def render_GET(self, request):
        htmlFile = self.bridgeRoot + "/manager/ssidform.html" 
        with open(htmlFile, 'r') as f:
            html = f.read()
        return html

    def render_POST(self, request):
        form = request.content.getvalue()
        #print ModuleName, "POST. form = ", form
        print "Credentials = ", request.args["ssid"][0], request.args["wpa"][0]
        response = "<html><font size=7>Thank you. Trying to connect.</font></html>"
        return response

class WifiConfig():
    def __init__(self, argv):
        self.bridgeRoot = os.getenv('CB_BRIDGE_ROOT', "/home/bridge/bridge")
        #print ModuleName, "CB_BRIDGE_ROOT = ", self.bridgeRoot
        reactor.listenTCP(80, Site(RootResource(self.bridgeRoot)))
        reactor.run()

    def stopReactor(self):
        try:
            reactor.stop()
        except:
             print ModuleName, self.id, " stop: reactor was not running"
        print ModuleName, "Bye from ", self.id
        sys.exit

if __name__ == '__main__':
    wifiConfig = WifiConfig(sys.argv)
