#!/usr/bin/python
ModuleName = "Accelapp2          " 

import sys
import os.path
import time
import json
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor

class App:
    def process(self, response):
        req = {}
        #print "response: ", response
        if response["id"] != "accel":
            pass
        if response["content"] == "data":
            #msg = {"id": "accelapp2",
            #       "msg": "testing"} 
            #managerFactory.protocol.sendMsg(msg)
            print "accel: ", response["data"] 
            req = {"id": "accelapp2",
                   "cmd": "send-accel"}
        elif response["content"] == "none" and response["status"] == "ok":
            req = {"id": "accelapp2",
                   "cmd": "send-accel"}
        return req 

    def processManagerCmd(self, cmd):
        print ModuleName, "Received from manager: ", cmd
        if cmd["cmd"] == "exit":
            msg = {"id": "accelapp2",
                   "msg": "exiting"} 
            reactor.stop()
            sys.exit
        else:
            print ModuleName, "Received unknown command from manager"
        return msg

class AccelADTClient(LineReceiver):
    def connectionMade(self):
        req = {"id": "accelapp2",
               "cmd": "init"} 
        self.sendLine(json.dumps(req) + "\r\n")

    def lineReceived(self, line):
        response = json.loads(line)
        req = app.process(response)
        self.sendLine(json.dumps(req) + "\r\n")

class ManagerClient(LineReceiver):
    def connectionMade(self):
        msg = {"id": "accelapp2",
               "msg": "hello"} 
        self.sendLine(json.dumps(msg) + "\r\n")

    def lineReceived(self, line):
        managerMsg = json.loads(line)
        msg = app.processManagerMsg(managerMsg)
        self.sendLine(json.dumps(msg) + "\r\n")

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

    if len(sys.argv) < 3:
        print "App improper usage"
        exit(1)
    
    managerSocket = sys.argv[1]
    adaptorSocket = sys.argv[2]
    
    app = App()
    accelADTfactory = cbClientFactory()
    accelADTfactory.protocol = AccelADTClient 
    reactor.connectUNIX(adaptorSocket, accelADTfactory, timeout=10)
    managerFactory = cbClientFactory()
    managerFactory.protocol = ManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    reactor.run()
    
