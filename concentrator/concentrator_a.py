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
import logging
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
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.status = "ok"
        self.readyApps = []
        self.conc_mode = os.getenv('CB_CONCENTRATOR', 'client')
        logging.info("%s CB_CONCENTRATOR = %s", ModuleName, self.conc_mode)

        if len(argv) < 3:
            logging.error("%s Improper number of arguments", ModuleName)
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        logging.info("%s Hello", ModuleName)

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
        #logging.info("%s onConfigure: %s", ModuleName, config)
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
            logging.info("%s onConfigure. appInstances: %s", ModuleName, self.appInstances)

    def onControllerMessage(self, msg):
        if "body" in msg:
            if not "connected" in msg["body"]:
                logging.debug("%s Received from controller: %s", ModuleName, json.dumps(msg, indent=4))
        try:
            if not "destination" in msg:
                msg["destination"] = self.bridge_id
        except Exception as inst:
            logging.warning("%s onControllerMessage. Unexpected message: %s", ModuleName, str(msg)[:100])
            logging.warning("%s Exception: %s %s", ModuleName, type(inst), str(inst.args))
            return
        if msg["destination"] == self.bridge_id:
            try:
                msg["status"] = "control_msg"
                msg["id"] = self.id
                if "message" in msg:
                    msg["type"] = msg.pop("message")
                self.cbSendManagerMsg(msg)
            except Exception as inst:
                logging.warning("%s onControllerMessage. Unexpected manager message: %s", ModuleName, str(msg)[:100])
                logging.warning("%s Exception: %s %s", ModuleName, type(inst), str(inst.args))
        else:
            try:
                dest = msg["destination"].split('/')
                if dest[0] == self.bridge_id:
                    if dest[1] in self.appInstances:
                        msg["destination"] = dest[1]
                        if dest[1] in self.readyApps:
                            logging.debug("%s onControllerMessage, sending to: %s %s", ModuleName, dest[1], str(msg)[:100])
                            self.cbSendMsg(msg, dest[1])
                        else:
                            logging.info("%s Received message before app ready: %s %s", ModuleName, dest[1], str(msg)[:100])
                else:
                    logging.warning("%s onControllerMessage. Received message with desination: %s", ModuleName, msg["destination"])
            except Exception as inst:
                logging.warning("%s onControllerMessage. Unexpected app message: %s", ModuleName, str(msg)[:100])
                logging.warning("%s Exception: %s %s", ModuleName, type(inst), str(inst.args))

    def onManagerMessage(self, msg):
        #logging.debug("%s Received from manager: %s", ModuleName, json.dumps(msg, indent=4))
        msg["time_sent"] = isotime()
        try:
            self.concFactory.sendMsg(msg)
        except Exception as inst:
            logging.warning("%s Failed to send message to bridge controller: %s", ModuleName, msg)
            logging.warning("%s Exception type: %s", ModuleName, type(inst))
            logging.warning("%s Exception args: %s", ModuleName, str(inst.args))

    def onManager(self, cmd):
        #logging.debug("%s Received from manager: %s", ModuleName, cmd)
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
        logging.info("%s Bye. Status: %s", ModuleName, status)
        sys.exit

    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def cbSendManagerMsg(self, msg):
        self.managerFactory.sendMsg(msg)

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
                        logging.warning("%s Message from app with no ID: %s", ModuleName, str(msg)[:100])
            elif not "destination" in msg:
                logging.warning("%s Message from app with no destination: %s", ModuleName, str(msg)[:100])
            else:
                if msg["destination"].startswith("CID"):
                    msg["source"] = self.bridge_id + "/" + msg["source"]
                    #logging.debug("%s Sending msg to cb: %s", ModuleName, str(msg)[:100])
                    self.concFactory.sendMsg(msg)
                else:
                    logging.warning("%s Illegal desination in app message: %s", ModuleName, str(msg)[:100])
        except Exception as inst:
            logging.warning("%s onAppData. Malformed message: %s", ModuleName, str(msg)[:100])
            logging.warning("%s Exception: %s %s", ModuleName, type(inst), str(inst.args))
    
if __name__ == '__main__':
    Concentrator(sys.argv)
