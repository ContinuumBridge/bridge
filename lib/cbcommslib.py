#!/usr/bin/env python
# cbcommslib.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
"""
self.status must be set by each app & adaptor to report back to the manager. Allowable values:
idle            Initial value at the start
configured      Should be set to indicate successful configuration
running         Indicates normal operation
please_restart  Something wrong. Requests the manager to restart the app
timeout         Not usually set by user apps
running should be set at least every 10 seconds as a heartbeat
"""

ModuleName = "cbLib" 
TIME_TO_MONITOR_STATUS = 60     # Time to wait before sending status messages to manager
SEND_STATUS_INTERVAL = 30       # Interval between sending status messages to manager
REACTOR_STOP_DELAY = 2          # Time to wait between telling app/adt to stop & stopping reactor

import sys
import os.path
import time
import json
import logging
import procname
from cbconfig import *
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.protocol import ClientFactory
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import defer
from twisted.internet import reactor
from data_store import DataStore, DataModel

def isotime():
    t = time.time()
    gmtime = time.gmtime(t)
    milliseconds = '%03d' % int((t - int(t)) * 1000)
    now = time.strftime('%Y-%m-%dT%H:%M:%S.', gmtime) + milliseconds +"Z"
    return now

class CbAdaptor:
    """This should be sub-classed by any app."""
    ModuleName = "CbAdaptor           " 

    def __init__(self, argv):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.doStop = False
        self.status = "ok"
        self.configured = False
        self.cbFactory = {}
        self.appInstances = []

        if len(argv) < 3:
            logging.error("%s cbAdaptor improper number of arguments", ModuleName)
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        logging.info("%s Hello from %s", ModuleName, self.id)
        procname.setprocname(self.id)

        initMsg = {"id": self.id,
                   "type": "adt",
                   "status": "req-config"} 
        self.managerFactory = CbClientFactory(self.processManager, initMsg)
        reactor.connectUNIX(managerSocket, self.managerFactory, timeout=10)

        reactor.callLater(TIME_TO_MONITOR_STATUS, self.sendStatus)
        reactor.run()

    def onConfigureMessage(self, config):
        """The adaptor should overwrite this and do all configuration in it."""
        logging.info("%s %s does not have onConfigureMessage", ModuleName, self.id)

    def onAppInit(self, message):
        """This should be overridden by the actual adaptor."""
        logging.warning("%s %s should subclass onAppInit method", ModuleName, self.id)

    def onAppRequest(self, message):
        """This should be overridden by the actual adaptor."""
        logging.warning("%s %s should subclass onAppRequest method", ModuleName, self.id)

    def onZwaveMessage(self, message):
        """This should be overridden by a Z-wave adaptor."""
        pass

    def onAppMessage(self, message):
        if "request" in message:
            if message["request"] == "init":
                self.onAppInit(message)
            elif message["request"] == "service": 
                self.onAppRequest(message)
            elif message["request"] == "command": 
                self.onAppCommand(message)
            else:
                logging.warning("%s %s Unexpected message from app: %s", ModuleName, self.id, message)
        else:
            logging.warning("%s %s No request field in message from app: %s", ModuleName, self.id, message)
 
    def onStop(self):
        """The adapotor should overwrite this if it needs to do any tidying-up before stopping"""
        pass

    def sendStatus(self):
        """ Send status to the manager at regular intervals as a heartbeat. """
        msg = {"id": self.id,
               "status": self.status}
        self.sendManagerMessage(msg)
        reactor.callLater(SEND_STATUS_INTERVAL, self.sendStatus)

    def cbConfigure(self, config):
        """Config is based on what apps are available."""
        #logging.debug("%s %s Configuration: %s ", ModuleName, self.id, config)
        self.name = config["name"]
        self.friendly_name = config["friendly_name"]
        self.device = config["btAdpt"]
        self.addr = config["btAddr"]
        self.sim = int(config["sim"])
        for app in config["apps"]:
            iName = app["id"]
            if iName not in self.appInstances:
                # configureig may be called again with updated config
                name = app["name"]
                adtSoc = app["adtSoc"]
                self.appInstances.append(iName)
                self.cbFactory[iName] = CbServerFactory(self.onAppMessage)
                reactor.listenUNIX(adtSoc, self.cbFactory[iName])
        if "zwave_socket" in config:
            initMsg = {"id": self.id,
                       "request": "init"}
            self.zwaveFactory = CbClientFactory(self.onZwaveMessage, initMsg)
            reactor.connectUNIX(config["zwave_socket"], self.zwaveFactory, timeout=10)
        self.onConfigureMessage(config)
        self.configured = True

    def processManager(self, cmd):
        #logging.debug("%s %s Received from manager: %s ", ModuleName, self.id, cmd)
        if cmd["cmd"] == "stop":
            self.onStop()
            self.doStop = True
            msg = {"id": self.id,
                   "status": "stopping"}
            #Adaptor must stop within REACTOR_STOP_DELAY seconds
            reactor.callLater(REACTOR_STOP_DELAY, self.stopReactor)
        elif cmd["cmd"] == "config":
            #Call in thread in case user code hangs
            reactor.callInThread(self.cbConfigure, cmd["config"]) 
            msg = {"id": self.id,
                   "status": "ok"}
        else:
            msg = {"id": self.id,
                   "status": self.status}
        self.sendManagerMessage(msg)
        # The adaptor must set self.status back to "running" as a heartbeat
        if self.status == "running":
            self.status = "timeout"

    def stopReactor(self):
        try:
            reactor.stop()
        except:
            logging.debug("%s %s stopReactor. Reactor was not running", ModuleName, self.id)
        logging.debug("%s Bye from %s", ModuleName, self.id)
        sys.exit

    def sendMessage(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def sendManagerMessage(self, msg):
        self.managerFactory.sendMsg(msg)

    def sendZwaveMessage(self, msg):
        self.zwaveFactory.sendMsg(msg)

class CbApp:
    """
    This should be sub-classed by any app.
    """
    ModuleName = "cbApp" 

    def __init__(self, argv):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.appClass = "none"       # Should be overwritten by app
        self.cbFactory = {}
        self.adtInstances = []
        self.doStop = False
        self.friendlyLookup = {}
        self.configured = False
        self.status = "ok"
        self.bridge_id = "unconfigure"

        if len(argv) < 3:
            logging.error("%s cbApp improper number of arguments", ModuleName)
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        logging.info("%s Hello from %s", ModuleName, self.id)
        procname.setprocname(self.id)

        initMsg = {"id": self.id,
                   "type": "app",
                   "status": "req-config"} 
        self.managerFactory = CbClientFactory(self.processManager, initMsg)
        reactor.connectUNIX(managerSocket, self.managerFactory, timeout=10)

        reactor.callLater(TIME_TO_MONITOR_STATUS, self.sendStatus)
        reactor.run()

    def onConcMessage(self, message):
        """This should be overridden by the actual app."""
        logging.warning("%s %s should subclass onConcMessage method", ModuleName, self.id)

    def onConfigureMessage(self, config):
        """The app should overwrite this and do all configuration in it."""
        logging.warning("%s %s should subclass onConfigureMessage method", ModuleName, self.id)

    def onStop(self):
        """The app should overwrite this and do all configuration in it."""
        pass

    def onAdaptorService(self, message):
        """This should be overridden by the actual app."""
        logging.warning("%s %s should subclass onAdaptorService method", ModuleName, self.id)

    def onAdaptorData(self, message):
        """This should be overridden by the actual app."""
        logging.warning("%s %s should subclass onAdaptorData method", ModuleName, self.id)

    def onAdaptorMessage(self, message):
        if message["content"] == "service":
            self.onAdaptorService(message)
        else:
            self.onAdaptorData(message)
 
    def sendStatus(self):
        """ Send status to the manager at regular intervals as a heartbeat. """
        msg = {"id": self.id,
               "status": self.status}
        self.sendManagerMessage(msg)
        reactor.callLater(SEND_STATUS_INTERVAL, self.sendStatus)

    def cbConfigure(self, config):
        """Config is based on what adaptors are available."""
        #logging.debug("%s %s Config: %s", ModuleName, self.id, config)
        # Connect to socket for each adaptor
        self.bridge_id = config["bridge_id"]
        for adaptor in config["adaptors"]:
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
                           "request": "init"}
                self.cbFactory[iName] = CbClientFactory(self.onAdaptorMessage, initMsg)
                reactor.connectUNIX(adtSoc, self.cbFactory[iName], timeout=10)
        # Connect to Concentrator socket
        if not self.configured:
            # Connect to the concentrator
            concSocket = config["concentrator"]
            initMsg = {"msg": "init",
                       "appID": self.id
                      }
            self.cbFactory["conc"] = CbClientFactory(self.onConcMessage, \
                                     initMsg)
            reactor.connectUNIX(concSocket, self.cbFactory["conc"], timeout=10)
            # Now call the app's configure method & set self.configured = True
            self.onConfigureMessage(config)
            self.configured = True

    def processManager(self, cmd):
        #logging.debug("%s %s Received from manager: %s", ModuleName, self.id, cmd)
        if cmd["cmd"] == "stop":
            self.onStop()
            self.doStop = True
            msg = {"id": self.id,
                   "status": "stopping"}
            #App must stop within REACTOR_STOP_DELAY seconds
            reactor.callLater(REACTOR_STOP_DELAY, self.stopReactor)
        elif cmd["cmd"] == "config":
            #Call in thread in case user code hangs
            reactor.callInThread(self.cbConfigure, cmd["config"]) 
            msg = {"id": self.id,
                   "status": "ok"}
        else:
            msg = {"id": self.id,
                   "status": self.status}
        self.sendManagerMessage(msg)
        # The app must set self.status back to "running" as a heartbeat
        if self.status == "running":
            self.status = "timeout"

    def stopReactor(self):
        try:
            reactor.stop()
        except:
            logging.warning("%s %s stopReactor when reactor not running", ModuleName, self.id)
        logging.info("%s Bye from %s", ModuleName, self.id)
        sys.exit

    def sendMessage(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def sendManagerMessage(self, msg):
        self.managerFactory.sendMsg(msg)

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
