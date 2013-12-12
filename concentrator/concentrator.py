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
from cbcommslib import cbClientFactory
from cbcommslib import cbManagerClient
from cbcommslib import cbAdaptorProtocol

class Concentrator():
    def __init__(self, argv):
        self.cbFactory = []
        self.status = "ok"
        self.doStop = False
        self.appData = {} 

        if len(argv) < 3:
            print "cbAdaptor improper number of arguments"
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        print ModuleName, "Hello from ", self.id

        managerFactory = cbClientFactory()
        managerFactory.protocol = cbManagerClient
        managerFactory.id = self.id
        managerFactory.protocol.id = self.id
        managerFactory.protocol.type = "conc"
        managerFactory.protocol.setStatus = self.setStatus
        managerFactory.protocol.reportStatus = self.reportStatus
        managerFactory.protocol.processManager = self.processManager
        reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
        reactor.run()

    def processConf(self, config):
        """Config is based on what apps are available."""
        self.cbFactory = []
        self.appInstances = []
        for app in config:
            appConcSoc = app["appConcSoc"]
            id = app["id"]
            print ModuleName, "app: ", id, " socket: ", appConcSoc
            self.appInstances.append(id)
            self.cbFactory.append(Factory())
            self.cbFactory[-1].protocol = cbAdaptorProtocol
            self.cbFactory[-1].protocol.processReqThread = self.processReqThread
            reactor.listenUNIX(appConcSoc, self.cbFactory[-1])
            self.appData[id] = []

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
        resp = self.processReq(req)
        return resp

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
        print ModuleName, "Req = ", req
        if req["req"] == "init" or req["req"] == "char":
           resp = {"name": "concentrator",
                   "id": self.id,
                   "status": concStatus,
                   "content": "none"}
        elif req["req"] == "put":
            self.appData[req["id"]].append(req["data"])
            resp = {"name": "concentrator",
                    "id": self.id,
                    "status": "ok",
                    "content": "data"} 
        else:
            resp = {"name": "concentrator",
                    "id": self.id,
                    "status": "bad-req",
                    "content": "none"}
        return resp

if __name__ == '__main__':
    concentrator = Concentrator(sys.argv)
