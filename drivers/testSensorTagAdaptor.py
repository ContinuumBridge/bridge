#!/usr/bin/env python

ModuleName = "SensorTag           "

import pexpect
import sys
import time
import os
import atexit
import pdb
import json
from twisted.internet.protocol import Protocol, Factory
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import reactor
from twisted.internet import threads
from twisted.internet import defer

class ManageTag:
    status = "ok"
    def __init__(self):
        self.connected = False
        self.status = "ok"
        self.fetchValues = True #Set to False to stop fetch thread
        self.accel = {} #To hold latest accel values
        self.temp = {}  #To hold temperature values
        self.accelReady = False #No accel values at start of time
        self.startTime = time.time()
        self.accelCount = 0
        self.tick = 0
        self.temp["ambT"] = 0
        self.temp["objT"] = 0
        self.temp["timeStamp"] = time.time()
        self.doingTemp = False

    def initSensorTag(self):
        return "ok"

    def reqAccel(self):
        time.sleep(1)
        self.accel["x"] = 17
        self.accel["y"] = 18
        self.accel["z"] =19
        self.accel["timeStamp"] = time.time()
        accel = self.accel
        return accel
 
    def reqTemp(self):
        self.temp["ambT"] = 22.0
        self.temp["objT"] = 23.0
        self.temp["timeStamp"] = time.time()
        return self.temp

    def processReq(self, req):
        """ Processes requests from apps """
        #print ModuleName, "processReq", req
        d1 = defer.Deferred()
        if req["req"] == "init" or req["req"] == "char":
            print ModuleName, id, " successfully initialised"
            resp = {"name": self.name,
                    "id": id,
                    "status": "ok",
                    "capabilities": {"accelerometer": "0.1",
                                     "temperature": "5"},
                    "content": "none"}
        elif req["req"] == "req-data":
            resp = {"name": self.name,
                    "id": id,
                    "status": "ok",
                    "content": "data", 
                    "accel": self.reqAccel(),
                    "temp": self.reqTemp()}
        else:
            resp = {"name": self.name,
                    "id": id,
                    "status": "bad-req",
                    "content": "none"}
        d1.callback(resp)
        return d1

    def configure(self, config):
        """ Config is based on what sensors are available """
        print ModuleName, "configure: ", config
        self.name = config["name"]
        self.device = config["btAdpt"]
        self.addr = config["btAddr"]
        self.cbFactory = []
        self.appInstances = []
        for app in config["apps"]:
            name = app["name"]
            id = app["id"]
            adtSoc = app["adtSoc"]
            self.appInstances.append(id)
            self.cbFactory.append(Factory())
            self.cbFactory[-1].protocol = cbAdaptorProtocol
            reactor.listenUNIX(adtSoc, self.cbFactory[-1])

    def cbManagerMsg(self, cmd):
        #print ModuleName, id, " received from manager: ", cmd
        if cmd["cmd"] == "stop":
            print ModuleName, id, " stopping"
            self.fetchValues = False
            msg = {"id": id,
                   "status": "stopping"}
            time.sleep(1)
            reactor.stop()
            sys.exit
        elif cmd["cmd"] == "config":
            self.configure(cmd["config"])
            msg = {"id": id,
                   "status": "ok"}
        elif cmd["cmd"] != "ok":
            msg = {"id": id,
                   "status": "unknown"}
        else:
            msg = {"id": id,
                   "status": "none"}
        return msg

    def reportStatus(self):
        return self.status

    def setStatus(self, newStatus):
        self.status = newStatus

class cbAdaptorProtocol(LineReceiver):
    def lineReceived(self, data):
        self.d1 = p.processReq(json.loads(data))
        self.d1.addCallback(self.sendResp)

    def sendResp(self, resp):
        self.sendLine(json.dumps(resp))

class cbManagerClient(LineReceiver):
    def connectionMade(self):
        msg = {"id": id,
               "class": "adt",
               "status": "req-config"}
        self.sendLine(json.dumps(msg))
        reactor.callLater(5, self.monitorProcess)

    def lineReceived(self, line):
        managerMsg = json.loads(line)
        msg = p.cbManagerMsg(managerMsg)
        if msg["status"] != "none":
            self.sendLine(json.dumps(msg))

    def monitorProcess(self):
        msg = {"id": id,
               "status": p.reportStatus()}
        self.sendLine(json.dumps(msg))
        p.setStatus("ok")
        reactor.callLater(2, self.monitorProcess)

class cbClientFactory(ReconnectingClientFactory):

    def clientConnectionFailed(self, connector, reason):
        print ModuleName, "Failed to connect:", \
              reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        print ModuleName, "Connection lost:", \
              reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

if __name__ == '__main__':
    print ModuleName, "Hello"
    
    if len(sys.argv) < 3:
        print ModuleName, "Wrong number of arguments"
        exit(1)
    
    managerSocket = sys.argv[1]
    id = sys.argv[2]
    
    p = ManageTag()
   
    # Socket for connecting to the bridge manager
    managerFactory = cbClientFactory()
    managerFactory.protocol = cbManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    
    reactor.run()
    
