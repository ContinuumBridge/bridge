#!/usr/bin/python
ModuleName = "cbApp               " 

import sys
import os.path
import time
import json
from pprint import pprint
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import reactor

class cbApp:
    """This should be sub-classed by any app."""

    def __init__(self, argv):
        self.cbFactory = []
        selfadtInstances = []
        self.status = "ok"
        self.doStop = False

        print ModuleName, "Hello"
        if len(argv) < 3:
            print "cbApp improper number of arguments"
            exit(1)
        
        managerSocket = argv[1]
        self.id = argv[2]
        
        managerFactory = cbClientFactory()
        managerFactory.protocol = cbManagerClient
        managerFactory.protocol.id = self.id
        managerFactory.protocol.class = "app"
        managerFactory.protocol.setStatus = self.setStatus
        managerFactory.protocol.reportStatus = self.reportStatus
        managerFactory.protocol.processManager = self.processManager
        reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
        reactor.run()

    def processResp(self, resp):
        """This should be overridden by the actual app."""
        req = {}
        self.status = "ok"
        req = {"id": self.id,
               "req": "none"}
        return req 

    def cbAppConfigure(self, config):
        """The app should overwrite this and do all configuration in it."""
        pass

    def processConf(self, config):
        """Config is based on what sensors are available."""
        print ModuleName, self.id, " configure: ", config
        for adaptor in config["adts"]:
            name = adaptor["name"]
            id = adaptor["id"]
            adtSoc = adaptor["adtSoc"]
            friendlyName = adaptor["friendlyName"]
            self.friendlyLookup.update({id: friendlyName})
            self.adtInstances.append(id)
            print ModuleName, "configure, adaptor name = ", name
            self.cbFactory.append(cbClientFactory())
            self.cbFactory[-1].protocol = cbAdaptorClient 
            self.cbFactory[-1].protocol.id = self.id 
            self.cbFactory[-1].protocol.processResp = self.processResp 
            reactor.connectUNIX(adtSoc, self.cbFactory[-1], timeout=10)
        self.cbAppConfigure(config)

    def processManager(self, cmd):
        #print ModuleName, "Received from manager: ", cmd
        if cmd["cmd"] == "stop":
            print ModuleName, self.id, " stopping"
            self.doStop = True
            msg = {"id": self.id,
                   "status": "stopping"}
            time.sleep(5)
            reactor.stop()
            sys.exit
        elif cmd["cmd"] == "config":
            self.processConf(cmd["config"]) 
            msg = {"id": self.id,
                   "status": "ok"}
        elif cmd["cmd"] != "ok":
            msg = {"id": self.id,
                   "status": "unknown"}
        else:
            msg = {"id": self.id,
                   "status": "none"}
        return msg

    def reportStatus(self):
        return self.status

    def setStatus(self, newStatus):
        self.status = newStatus

class cbAdaptorClient(LineReceiver):
    def connectionMade(self):
        req = {"id": self.id,
               "req": "init"}
        self.sendLine(json.dumps(req))

    def lineReceived(self, data):
        resp = json.loads(data)
        req = self.processResp(resp)
        self.sendLine(json.dumps(req))

class cbManagerClient(LineReceiver):
    def connectionMade(self):
        print ModuleName, "self.id = ", self.id
        msg = {"id": self.id,
               "class": self.class
               "status": "req-config"} 
        self.sendLine(json.dumps(msg))
        reactor.callLater(5, self.monitorProcess)

    def lineReceived(self, line):
        managerMsg = json.loads(line)
        msg = self.processManager(managerMsg)
        if msg["status"] != "none":
            self.sendLine(json.dumps(msg))

    def monitorProcess(self):
        msg = {"id": self.id,
               "status": self.reportStatus()}
        self.sendLine(json.dumps(msg))
        self.setStatus("ok")
        reactor.callLater(2, self.monitorProcess)

class cbClientFactory(ReconnectingClientFactory):
    """Tries to reconnect to socket if connection lost."""
    def clientConnectionFailed(self, connector, reason):
        print ModuleName, "Failed to connect:"
        print ModuleName,  reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        print ModuleName, "Connection lost:"
        print ModuleName, reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

class cbAppProtocol(LineReceiver):
    def connectionMade(self):
        msg = {"id": id,
               "status": "ready"}
        self.sendLine(json.dumps(msg))
        reactor.callLater(30, self.monitorApp)

    def lineReceived(self, line):
        print ModuleName, line

    def monitorApp(self):
        reactor.callLater(1, self.monitorApp)

class cbAdaptorProtocol(LineReceiver):
    def lineReceived(self, data):
        self.d1 = p.processReq(json.loads(data))
        self.d1.addCallback(self.sendResp)

    def sendResp(self, resp):
        self.sendLine(json.dumps(resp))

