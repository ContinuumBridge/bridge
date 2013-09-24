#!/usr/bin/python
ModuleName = "Accelapp2           " 
id = "accelapp2"

import sys
import os.path
import time
import json
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import reactor

class App:
    status = "ok"
    def __init___(self):
        self.status = "ok"

    def process(self, response):
        req = {}
        #print "response: ", response
        if response["id"] != "accel":
            pass
        if response["content"] == "data":
            print "accel: ", response["data"] 
            req = {"id": id,
                   "cmd": "send-accel"}
        elif response["content"] == "none" and response["status"] == "ok":
            req = {"id": id,
                   "cmd": "send-accel"}
        else:
            # A problem has occured. Report it to bridge manager
            self.status = "adaptor problem"
        return req 

    def processManagerMsg(self, cmd):
        #print ModuleName, "Received from manager: ", cmd
        if cmd["cmd"] == "stop":
            print ModuleName, "Stopping"
            msg = {"id": id,
                   "status": "stopping"}
            reactor.stop()
            sys.exit
        elif cmd["cmd"] != "ok":
            msg = {"id": id,
                   "status": "unknown"}
        else:
            msg = {"status": "none"}
        return msg

    def reportStatus(self):
        return self.status

    def setStatus(self, newStatus):
        self.status = newStatus

class AccelADTClient(LineReceiver):
    def connectionMade(self):
        req = {"id": id,
               "cmd": "init"} 
        self.sendLine(json.dumps(req) + "\r\n")

    def lineReceived(self, line):
        response = json.loads(line)
        req = p.process(response)
        self.sendLine(json.dumps(req) + "\r\n")

class ManagerClient(LineReceiver):
    def connectionMade(self):
        msg = {"id": id,
               "status": "hello"} 
        self.sendLine(json.dumps(msg))
        reactor.callLater(5, self.monitorProcess)

    def lineReceived(self, line):
        managerMsg = json.loads(line)
        msg = p.processManagerMsg(managerMsg)
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
        print "App improper usage"
        exit(1)
    
    managerSocket = sys.argv[1]
    adaptorSocket = sys.argv[2]
    
    p = App()
    accelADTfactory = cbClientFactory()
    accelADTfactory.protocol = AccelADTClient 
    reactor.connectUNIX(adaptorSocket, accelADTfactory, timeout=10)
    managerFactory = cbClientFactory()
    managerFactory.protocol = ManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    reactor.run()
    
