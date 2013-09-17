#!/usr/bin/python
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
            print "accel: ", response["data"] 
            req = {"id": "accelapp2",
                   "cmd": "send-accel"}
        elif response["content"] == "none" and response["status"] == "ok":
            req = {"id": "accelapp2",
                   "cmd": "send-accel"}
        return req 

class AccelADTClient(LineReceiver):
    def connectionMade(self):
        req = {"id": "accelapp2",
               "cmd": "init"} 
        self.sendLine(json.dumps(req) + "\r\n")

    def lineReceived(self, line):
        response = json.loads(line)
        req = app.process(response)
        self.sendLine(json.dumps(req) + "\r\n")

class AccelADTClientFactory(ReconnectingClientFactory):
    protocol = AccelADTClient

    def clientConnectionFailed(self, connector, reason):
        print 'accelapp2 failed to connect to adaptor:', reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        print 'accelapp2 connection to adaptor lost:', reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

if __name__ == '__main__':

    if len(sys.argv) < 3:
        print "App improper usage"
        exit(1)
    
    mgrSocket = sys.argv[1]
    adaptorSocket = sys.argv[2]
    
    app = App()
    AccelADTfactory = AccelADTClientFactory()
    reactor.connectUNIX(adaptorSocket, AccelADTfactory, timeout=10)
    reactor.run()
    
