#!/usr/bin/env python
# cbcommslib.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "cbLib               " 

import sys
import os.path
import time
import json
from pprint import pprint
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
        self.status = "ok"
        self.doStop = False
        self.configured = False
        self.cbFactory = {}
        self.appInstances = []

        if len(argv) < 3:
            print "CbAdaptor improper number of arguments"
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        print ModuleName, "Hello from ", self.id

        initMsg = {"id": self.id,
                   "type": "adt",
                   "status": "req-config"} 
        managerFactory = CbClientFactory(self.processManager, initMsg)
        reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
        reactor.run()

    def cbAdtConfigure(self, config):
        """The app should overwrite this and do all configuration in it."""
        print ModuleName, "The wrong cbAdtConfigure"

    def processConf(self, config):
        """Config is based on what apps are available."""
        #print ModuleName, self.id, " configure: "
        #pprint(config)
        self.name = config["name"]
        self.friendlyName = config["friendlyName"]
        self.device = config["btAdpt"]
        self.addr = config["btAddr"]
        for app in config["apps"]:
            iName = app["id"]
            if iName not in self.appInstances:
                # processConfig may be called again with updated config
                name = app["name"]
                adtSoc = app["adtSoc"]
                self.appInstances.append(iName)
                self.cbFactory[iName] = CbServerFactory(self.processReqThread)
                reactor.listenUNIX(adtSoc, self.cbFactory[iName])
        if not self.configured:
            self.cbAdtConfigure(config)
            self.configured = True

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

class CbApp:
    """This should be sub-classed by any app."""
    ModuleName = "cbApp               " 

    def __init__(self, argv):
        self.cbFactory = {}
        self.adtInstances = []
        self.status = "ok"
        self.doStop = False
        self.friendlyLookup = {}
        self.configured = False

        if len(argv) < 3:
            print "cbApp improper number of arguments"
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        print ModuleName, "Hello from ", self.id

        initMsg = {"id": self.id,
                   "type": "app",
                   "status": "req-config"} 
        managerFactory = CbClientFactory(self.processManager, initMsg)
        reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
        reactor.run()

    def processResp(self, resp):
        """This should be overridden by the actual app."""
        print ModuleName, self.id, " should subclass processResp"

    def processConcResp(self, resp):
        """This should be overridden by the actual app."""
        print ModuleName, self.id, "should subclass processConcResp"

    def cbAppConfigure(self, config):
        """The app should overwrite this and do all configuration in it."""
        print ModuleName, self.id, " should subclass cbAppConfigure"

    def processConf(self, config):
        """Config is based on what adaptors are available."""
        print ModuleName, self.id, " configure: "
        pprint(config)
        # Connect to socket for each adaptor
        for adaptor in config["adts"]:
            iName = adaptor["id"]
            if iName not in self.adtInstances:
                # Allows for adding extra adaptors on the fly
                name = adaptor["name"]
                adtSoc = adaptor["adtSoc"]
                friendlyName = adaptor["friendlyName"]
                self.friendlyLookup.update({iName: friendlyName})
                self.adtInstances.append(iName)
                initMsg = {"id": self.id,
                           "appClass": self.appClass,
                           "req": "init"}
                self.cbFactory[iName] = CbClientFactory(self.processRespThread, \
                                        initMsg)
                reactor.connectUNIX(adtSoc, self.cbFactory[iName], timeout=10)
        # Connect to Concentrator socket
        if not self.configured:
            # Connect to the concentrator
            concSocket = config["concentrator"]
            initMsg = {"appID": self.id,
                       "req": "init"}
            self.cbFactory["conc"] = CbClientFactory(self.processConcResp, \
                                     initMsg)
            reactor.connectUNIX(concSocket, self.cbFactory["conc"], timeout=10)
            # Now call the app's configure method & set self.configured = True
            self.cbAppConfigure(config)
            self.configured = True

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

    def processRespThread(self, resp):
        """Simplifies calling the app's processResp in a Twisted thread."""
        self.processResp(resp)

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
