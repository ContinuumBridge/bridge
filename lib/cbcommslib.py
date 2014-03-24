#!/usr/bin/env python
# cbcommslib.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "cbLib" 

import sys
import os.path
import time
import json
import logging
from cbconfig import *
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.protocol import ClientFactory
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import defer
from twisted.internet import reactor

class CbAdaptor:
    """This should be sub-classed by any app."""
    ModuleName = "CbAdaptor           " 

    def __init__(self, argv):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.doStop = False
        self.configured = False
        self.cbFactory = {}
        self.appInstances = []

        if len(argv) < 3:
            logging.error("%s cbAdaptor improper number of arguments", ModuleName)
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        logging.info("%s Hello from %s", ModuleName, self.id)

        initMsg = {"id": self.id,
                   "type": "adt",
                   "status": "req-config"} 
        self.managerFactory = CbClientFactory(self.processManager, initMsg)
        reactor.connectUNIX(managerSocket, self.managerFactory, timeout=10)
        reactor.run()

    def cbAdtConfigure(self, config):
        """The app should overwrite this and do all configuration in it."""
        logging.warning("%s %s The wrong cbAdtConfigure method", ModuleName, self.id)

    def processConf(self, config):
        """Config is based on what apps are available."""
        logging.debug("%s %s Configuration: %s ", ModuleName, self.id, config)
        self.name = config["name"]
        self.friendly_name = config["friendly_name"]
        self.device = config["btAdpt"]
        self.addr = config["btAddr"]
        self.sim = int(config["sim"])
        for app in config["apps"]:
            iName = app["id"]
            if iName not in self.appInstances:
                # processConfig may be called again with updated config
                name = app["name"]
                adtSoc = app["adtSoc"]
                self.appInstances.append(iName)
                self.cbFactory[iName] = CbServerFactory(self.processReq)
                reactor.listenUNIX(adtSoc, self.cbFactory[iName])
        self.cbAdtConfigure(config)
        self.configured = True

    def processManager(self, cmd):
        logging.debug("%s %s Received from manager: %s ", ModuleName, self.id, cmd)
        if cmd["cmd"] == "stop":
            self.doStop = True
            msg = {"id": self.id,
                   "status": "stopping"}
            #Adaptor must check stop in less than 20 seconds
            reactor.callLater(20, self.stopReactor)
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
        self.managerFactory.sendMsg(msg)

    def stopReactor(self):
        try:
            reactor.stop()
        except:
            logging.debug("%s %s stopReactor. Reactor was not running", ModuleName, self.id)
        logging.debug("%s Bye from %s", ModuleName, self.id)
        sys.exit

    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

class CbApp:
    """This should be sub-classed by any app."""
    ModuleName = "cbApp               " 

    def __init__(self, argv):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.cbFactory = {}
        self.adtInstances = []
        self.doStop = False
        self.friendlyLookup = {}
        self.configured = False

        if len(argv) < 3:
            logging.error("%s cbApp improper number of arguments", ModuleName)
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        logging.info("%s Hello from %s", ModuleName, self.id)

        initMsg = {"id": self.id,
                   "type": "app",
                   "status": "req-config"} 
        self.managerFactory = CbClientFactory(self.processManager, initMsg)
        reactor.connectUNIX(managerSocket, self.managerFactory, timeout=10)
        reactor.run()

    def processResp(self, resp):
        """This should be overridden by the actual app."""
        logging.warning("%s %s should subclass processResp method", ModuleName, self.id)

    def processConcResp(self, resp):
        """This should be overridden by the actual app."""
        logging.warning("%s %s should subclass processConcResp method", ModuleName, self.id)

    def cbAppConfigure(self, config):
        """The app should overwrite this and do all configuration in it."""
        logging.warning("%s %s should subclass cbAppConfigure method", ModuleName, self.id)

    def processConf(self, config):
        """Config is based on what adaptors are available."""
        logging.debug("%s %s Config: %s", ModuleName, self.id, config)
        # Connect to socket for each adaptor
        for adaptor in config["adts"]:
            iName = adaptor["id"]
            if iName not in self.adtInstances:
                # Allows for adding extra adaptors on the fly
                name = adaptor["name"]
                adtSoc = adaptor["adtSoc"]
                friendly_name = adaptor["friendly_name"]
                self.friendlyLookup.update({iName: friendly_name})
                self.adtInstances.append(iName)
                initMsg = {"id": self.id,
                           "appClass": self.appClass,
                           "req": "init"}
                self.cbFactory[iName] = CbClientFactory(self.processResp, initMsg)
                reactor.connectUNIX(adtSoc, self.cbFactory[iName], timeout=10)
        # Connect to Concentrator socket
        if not self.configured:
            # Connect to the concentrator
            concSocket = config["concentrator"]
            initMsg = {"msg": "init",
                       "appID": self.id
                      }
            self.cbFactory["conc"] = CbClientFactory(self.processConcResp, \
                                     initMsg)
            reactor.connectUNIX(concSocket, self.cbFactory["conc"], timeout=10)
            # Now call the app's configure method & set self.configured = True
            self.cbAppConfigure(config)
            self.configured = True

    def processManager(self, cmd):
        logging.debug("%s %s Received from manager: %s", ModuleName, self.id, cmd)
        if cmd["cmd"] == "stop":
            self.doStop = True
            msg = {"id": self.id,
                   "status": "stopping"}
            #App must stop within 20 seconds
            reactor.callLater(20, self.stopReactor)
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
        self.managerFactory.sendMsg(msg)

    def stopReactor(self):
        try:
            reactor.stop()
        except:
            logging.warning("%s %s stopReactor when reactor not running", ModuleName, self.id)
        logging.info("%s Bye from %s", ModuleName, self.id)
        sys.exit

    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

class CbClientProtocol(LineReceiver):
    def __init__(self, processMsg, initMsg):
        self.processMsg = processMsg
        self.initMsg = initMsg

    def connectionMade(self):
        self.sendLine(json.dumps(self.initMsg))

    def lineReceived(self, data):
        self.processMsg(json.loads(data))

    def sendMsg(self, msg):
        self.sendLine(json.dumps(msg))

class CbClientFactory(ClientFactory):
    def __init__(self, processMsg, initMsg):
        self.processMsg = processMsg
        self.initMsg = initMsg

    def buildProtocol(self, addr):
        self.proto = CbClientProtocol(self.processMsg, self.initMsg)
        return self.proto

    def sendMsg(self, msg):
        self.proto.sendMsg(msg)

class CbServerProtocol(LineReceiver):
    def __init__(self, processMsg):
        self.processMsg = processMsg

    def lineReceived(self, data):
        self.processMsg(json.loads(data))

    def sendMsg(self, msg):
        self.sendLine(json.dumps(msg))

class CbServerFactory(Factory):
    def __init__(self, processMsg):
        self.processMsg = processMsg

    def buildProtocol(self, addr):
        self.proto = CbServerProtocol(self.processMsg)
        return self.proto

    def sendMsg(self, msg):
        self.proto.sendMsg(msg)
