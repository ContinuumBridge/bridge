#!/usr/bin/env python
# concentrator.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Concentrator"

import sys
import time
import os
import json
import procname
from twisted.internet.protocol import Protocol, Factory
from twisted.protocols.basic import LineReceiver
from twisted.internet import threads
from twisted.internet import defer
from twisted.internet import reactor
from cbcommslib import CbClientProtocol
from cbcommslib import CbClientFactory
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory
from cbcommslib import isotime
from cbconfig import *

class Concentrator():
    def __init__(self, argv):
        procname.setprocname('concentrator')
        self.status = "ok"
        self.readyApps = []
        self.conc_mode = os.getenv('CB_CONCENTRATOR', 'client')

        if len(argv) < 3:
            self.cbLog("error", "Improper number of arguments")
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]

        # Connection to manager
        initMsg = {"id": self.id,
                   "type": "conc",
                   "status": "req-config"} 
        self.managerFactory = CbClientFactory(self.onManager, initMsg)
        self.managerConnect = reactor.connectUNIX(managerSocket, self.managerFactory, timeout=10)

        # Connection to conduit process
        initMsg = {"type": "status",
                   "time_sent": isotime(),
                   "body": "bridge manager started"}
        self.concFactory = CbClientFactory(self.onControllerMessage, initMsg)
        self.jsConnect = reactor.connectTCP("localhost", 5000, self.concFactory, timeout=30)

        reactor.run()

    def onConfigure(self, config):
        """Config is based on what apps are available."""
        #self.cbLog("info", "onConfigure: " + str(config))
        self.bridge_id = config["bridge_id"]
        if "apps" in config:
            self.cbFactory = {}
            self.appInstances = []
            for app in config["apps"]:
                iName = app["id"]
                if iName not in self.appInstances:
                    # Allows for reconfig on the fly
                    appConcSoc = app["appConcSoc"]
                    self.appInstances.append(iName)
                    self.cbFactory[iName] = CbServerFactory(self.onAppData)
                    reactor.listenUNIX(appConcSoc, self.cbFactory[iName])
            self.cbLog("info", "onConfigure. appInstances: " + str(self.appInstances))

    def onControllerMessage(self, msg):
        if "body" in msg:
            if not "connected" in msg["body"]:
                self.cbLog("debug", "Received from controller: " + str(json.dumps(msg, indent=4)))
        try:
            if not "destination" in msg:
                msg["destination"] = self.bridge_id
        except Exception as inst:
            self.cbLog("warning", "onControllerMessage. Unexpected message: " + str(json.dumps(msg, indent=4)))
            self.cbLog("warning", "Exception: " + str(type(inst)) + " " +  str(inst.args))
            return
        if msg["destination"] == self.bridge_id or msg["destination"] == "broadcast":
            try:
                msg["status"] = "control_msg"
                msg["id"] = self.id
                if "message" in msg:
                    msg["type"] = msg.pop("message")
                self.cbSendManagerMsg(msg)
            except Exception as inst:
                self.cbLog("warning", "onControllerMessage. Unexpected manager message: " + str(json.dumps(msg, indent=4)))
                self.cbLog("warning", "Exception: " + str(type(inst)) + " " +  str(inst.args))
        else:
            try:
                dest = msg["destination"].split('/')
                if dest[0] == self.bridge_id:
                    if dest[1] in self.appInstances:
                        msg["destination"] = dest[1]
                        if dest[1] in self.readyApps:
                            self.cbLog("debug", "onControllerMessage, sending to: " +  dest[1])
                            self.cbSendMsg(msg, dest[1])
                        else:
                            self.cbLog("info", "Received message before app ready: " + dest[1])
                else:
                    self.cbLog("warning", "onControllerMessage. Received message with desination: " + msg["destination"])
            except Exception as inst:
                self.cbLog("warning", "onControllerMessage. Unexpected app message: " + str(json.dumps(msg, indent=4)))
                self.cbLog("warning", "Exception: " + str(type(inst)) + " " +  str(inst.args))

    def onManagerMessage(self, msg):
        #self.cbLog("debug", "Received from manager: " + str(json.dumps(msg, indent=4)))
        msg["time_sent"] = isotime()
        try:
            self.concFactory.sendMsg(msg)
        except Exception as inst:
            self.cbLog("warning", "Failed to send message to bridge controller: " + str(msg))
            self.cbLog("warning", "Exception: " + str(type(inst)) + " " +  str(inst.args))

    def onManager(self, cmd):
        if cmd["cmd"] == "msg":
            self.onManagerMessage(cmd["msg"])
            msg = {"id": self.id,
                   "status": "ok"}
        elif cmd["cmd"] == "stop":
            msg = {"id": self.id,
                   "status": "stopping"}
            reactor.callLater(0.2, self.doStop)
        elif cmd["cmd"] == "config":
            self.onConfigure(cmd["config"])
            msg = {"id": self.id,
                   "status": "ready"}
        else:
            msg = {"id": self.id,
                   "status": "ok"}
        self.cbSendManagerMsg(msg)

    def doStop(self):
        d1 = defer.maybeDeferred(self.jsConnect.disconnect)
        d2 = defer.maybeDeferred(self.managerConnect.disconnect)
        d = defer.gatherResults([d1, d2], consumeErrors=True)
        d.addCallback(self.goodbye)

    def goodbye(self, status):
        reactor.stop()

    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def cbSendManagerMsg(self, msg):
        self.managerFactory.sendMsg(msg)

    def cbLog(self, level, log):
        msg = {"id": self.id,
               "status": "log",
               "level": level,
               "body": log}
        self.cbSendManagerMsg(msg)

    def appInit(self, appID):
        resp = {"id": "conc",
                "resp": "config"}
        self.cbSendMsg(resp, appID)
        self.readyApps.append(appID)

    def onAppData(self, msg):
        """
        Processes requests from apps.
        Called separately for every app that can make msguests.
        """
        try:
            if "msg" in msg:
                if msg["msg"] == "init":
                    if "appID" in msg:
                        self.appInit(msg["appID"])
                    else:
                        self.cbLog("warning", "Message from app with no ID: " + str(msg)[:100])
            elif not "destination" in msg:
                self.cbLog("warning", "Message from app with no destination: " + str(msg)[:100])
            else:
                if msg["destination"].startswith("CID"):
                    msg["source"] = self.bridge_id + "/" + msg["source"]
                    self.concFactory.sendMsg(msg)
                else:
                    self.cbLog("warning","Illegal desination in app message: " + str(msg)[:100])
        except Exception as inst:
            self.cbLog("warning", "onAppData. Malformed message: " + str(msg)[:100])
            self.cbLog("warning", "Exception: " + str(type(inst)) + str(inst.args))
    
if __name__ == '__main__':
    Concentrator(sys.argv)
