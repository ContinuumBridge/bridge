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
from twisted.application.internet import TCPServer
from twisted.application.service import Application
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet.task import deferLater
from twisted.web.server import NOT_DONE_YET
from cbcommslib import CbManagerClientFactory
from cbcommslib import CbManagerClient
from cbcommslib import CbServerFactory

class DataStore():
    def __init__(self):
        self.config = {}
        self.appData = {}

    def setConfig(self, config):
        self.config = config

    def getConfig(self):
        return self.config

    def appendData(self, device, type, data):
        self.appData[device].append({type: data})
        #print ModuleName, "appendData = ", device, data

    def addDevice(self, d):
        self.appData[d] = []

    def deviceKnown(self, d):
        if d in self.appData:
            return True
        else:
            return False

    def getData(self, device):
        data = self.appData[device]
        self.appData[device] = [] 
        return data

class DevicePage(Resource):
    isLeaf = True
    def __init__(self, dataStore):
        self.dataStore = dataStore
        Resource.__init__(self)

    def _delayedRender(self, request):
        data = self.dataStore.getData(self.currentDev)
        if data == []:
            d = deferLater(reactor, 0.33, lambda: request)
            d.addCallback(self._delayedRender)
            return NOT_DONE_YET
        else:
            request.setHeader('Content-Type', 'application/json')
            response = {"device": self.currentDev,
                        "data": data}
            request.write(json.dumps(response))
            request.finish()

    def render_GET(self, request):
        reqParts = str(request).split(" ")
        self.currentDev = reqParts[4][12:]
        #print ModuleName, "render_GET for ", self.currentDev
        try:
            data = self.dataStore.getData(self.currentDev)
        except:
            request.setHeader('Content-Type', 'application/json')
            #request.setHeader('Status', '404')
            response = {"device": self.currentDev,
                        "status": "Error. No data for device"}
            return json.dumps(response)
        if data == []:
            d = deferLater(reactor, 5, lambda: request)
            d.addCallback(self._delayedRender)
            return NOT_DONE_YET
        else:
            request.setHeader('Content-Type', 'application/json')
            response = {"device": self.currentDev,
                        "data": data}
            return json.dumps(response)

class ConfigPage(Resource):
    isLeaf = True
    def __init__(self, dataStore):
        self.dataStore = dataStore
        Resource.__init__(self)

    def render_GET(self, request):
        request.setHeader('Content-Type', 'application/json')
        config = self.dataStore.getConfig()
        response = {"config": config}
        return json.dumps(response)

    def render_POST(self, request):
        request.setHeader('Content-Type', 'application/json')
        req = json.loads(request.content.getvalue())
        print ModuleName, "POST. req = ", req
        response = {"resp": "ok"}
        return json.dumps(response)

class RootResource(Resource):
    isLeaf = False
    def __init__(self, dataStore):
        self.dataStore = dataStore
        Resource.__init__(self)
        self.putChild('config', ConfigPage(self.dataStore))
        self.putChild('device', DevicePage(self.dataStore))

class Concentrator():
    def __init__(self, argv):
        self.status = "ok"
        self.doStop = False

        if len(argv) < 3:
            print "cbAdaptor improper number of arguments"
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        print ModuleName, "Hello from ", self.id

        self.dataStore = DataStore()
        managerFactory = CbManagerClientFactory()
        managerFactory.protocol = CbManagerClient
        managerFactory.id = self.id
        managerFactory.protocol.id = self.id
        managerFactory.protocol.type = "conc"
        managerFactory.protocol.setStatus = self.setStatus
        managerFactory.protocol.reportStatus = self.reportStatus
        managerFactory.protocol.processManager = self.processManager
        reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
        reactor.listenTCP(8880, Site(RootResource(self.dataStore)))
        reactor.run()

    def processConf(self, config):
        """Config is based on what apps are available."""
        print ModuleName, "processConf: ", config
        self.cbFactory = {}
        self.appInstances = []
        for app in config:
            appConcSoc = app["appConcSoc"]
            iName = app["id"]
            print ModuleName, "app: ", iName, " socket: ", appConcSoc
            self.appInstances.append(iName)
            self.cbFactory[iName] = CbServerFactory(self.processReqThread)
            reactor.listenUNIX(appConcSoc, self.cbFactory[iName])

    def processManager(self, cmd):
        #print ModuleName, "Received from manager: ", cmd
        if cmd["cmd"] == "stop":
            self.doStop = True
            msg = {"id": self.id,
                   "status": "stopping"}
            #Adaptor must check doStop more often than every 8 seconds
            reactor.callLater(8, self.stopReactor)
        elif cmd["cmd"] == "config":
            #Call in thread in case user code hangs
            reactor.callInThread(self.processConf, cmd["config"])
            msg = {"id": self.id,
                   "status": "ok"}
        elif cmd["cmd"] != "ok":
            msg = {"id": self.id,
                   "status": "unknown"}
        else:
            msg = {"id": self.id,
                   "status": "none"}
        return msg

    def stopReactor(self):
        try:
            reactor.stop()
        except:
             print ModuleName, self.id, " stop: reactor was not running"
        print ModuleName, "Bye from ", self.id
        sys.exit

    def processReqThread(self, req):
        """Simplifies calling the adaptor's processReq in a Twisted thread."""
        self.processReq(req)

    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def reportStatus(self):
        return self.status

    def setStatus(self, newStatus):
        self.status = newStatus

    def processReq(self, req):
        """
        Processes requests from apps.
        Called in a thread and so it is OK if it blocks.
        Called separately for every app that can make requests.
        """
        #print ModuleName, "processReq, Req = ", req
        if req["req"] == "init":
            print ModuleName, "init from app ", req["appID"]
            if req["appID"] == "app1":
                resp = {"id": "conc",
                        "resp": "config"}
                self.cbSendMsg(resp, req["appID"])
        elif req["req"] == "services":
            for s in req["services"]:
                self.dataStore.addDevice(s["id"])
            self.dataStore.setConfig(req["services"])
        elif req["req"] == "put":
            if req["appID"] == "app1": 
                if self.dataStore.deviceKnown(req["deviceID"]):
                    self.dataStore.appendData(req["deviceID"], req["type"], \
                        req["data"])
                else:
                    # Unknown device, request config update
                    resp = {"id": "conc",
                            "resp": "config"}
                    self.cbSendMsg(resp, req["appID"])
        else:
            pass

if __name__ == '__main__':
    concentrator = Concentrator(sys.argv)
