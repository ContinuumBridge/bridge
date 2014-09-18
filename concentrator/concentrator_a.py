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
from cbconfig import *

class Concentrator():
    def __init__(self, argv):
        procname.setprocname('concentrator')
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.status = "ok"
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
        self.managerFactory = CbClientFactory(self.processManager, initMsg)
        self.managerConnect = reactor.connectUNIX(managerSocket, self.managerFactory, timeout=10)

        # Connection to conduit process
        initMsg = {"type": "status",
                   "time_sent": self.isotime(),
                   "body": "bridge manager started"}
        self.concFactory = CbClientFactory(self.processServerMsg, initMsg)
        self.jsConnect = reactor.connectTCP("localhost", 5000, self.concFactory, timeout=10)

        reactor.run()

    def processConf(self, config):
        """Config is based on what apps are available."""
        #logging.info("%s processConf: %s", ModuleName, config)
        if config != "no_apps":
            self.bridge_id = config["bridge_id"]
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

    def processServerMsg(self, msg):
        #logging.debug("%s Received from controller: %s", ModuleName, str(msg)[:100])
        msg["status"] = "control_msg"
        msg["id"] = self.id
        if "message" in msg:
            msg["type"] = msg.pop("message")
        self.cbSendManagerMsg(msg)

    def isotime(self):
        t = time.time()
        gmtime = time.gmtime(t)
        milliseconds = '%03d' % int((t - int(t)) * 1000)
        now = time.strftime('%Y-%m-%dT%H:%M:%S.', gmtime) + milliseconds +"Z"
        return now

    def processManagerMsg(self, msg):
        #logging.debug("%s Received from manager: %s", ModuleName, msg)
        msg["time_sent"] = self.isotime()
        self.concFactory.sendMsg(msg)

    def processManager(self, cmd):
        #logging.debug("%s Received from manager: %s", ModuleName, cmd)
        if cmd["cmd"] == "msg":
            self.processManagerMsg(cmd["msg"])
            msg = {"id": self.id,
                   "status": "ok"}
        elif cmd["cmd"] == "stop":
            msg = {"id": self.id,
                   "status": "stopping"}
            reactor.callLater(0.2, self.doStop)
        elif cmd["cmd"] == "config":
            self.processConf(cmd["config"])
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
        """ Request delayed to give app time to configure. """
        resp = {"id": "conc",
                "resp": "config"}
        self.cbSendMsg(resp, appID)

    def onAppData(self, msg):
        """
        Processes requests from apps.
        Called separately for every app that can make msguests.
        """
        if not "destination" in msg:
            logging.warning("%s Message from app with no destination: %s", ModuleName, str(msg))
        else:
            if msg["destination"].startswith("CID"):
                msg["source"] = self.bridge_id + "/" + msg["source"]
                logging.debug("%s Sending msg to cb: %s", ModuleName, str(msg))
                self.concFactory.sendMsg(msg)
            else:
                logging.warning("%s Illegal desination in app message: %s", ModuleName, str(msg))

if __name__ == '__main__':
    Concentrator(sys.argv)
