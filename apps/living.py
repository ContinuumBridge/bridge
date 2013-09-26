#!/usr/bin/python
ModuleName = "Living              " 
id = "living"

import sys
import os.path
import time
import json
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import reactor

class Accelerometer:
    """ Takes x, y, z accelerometer values & produces an energy output.
        The energy output is the deviation of the absolute values from
        a moving average that is calculated over the last averageLength
        samples. """

    averageLength = 64 
    Loc = 0
    total = [0.0, 0.0, 0.0]
    learnt = False
    values = []

    def __init__(self):
        for i in xrange(self.averageLength):
            self.values.append([0.0, 0.0, 0.0])

    def detectEvent(self, accel):
        """ Compute moving averages for x, y and z over averageLen samples """
        av = [0.0, 0.0, 0.0]
        for i in xrange(3):
            self.total[i] = self.total[i] - self.values[self.Loc][i] + accel[i]
            self.values[self.Loc][i] = accel[i]
            av[i] = self.total[i]/self.averageLength
        if self.Loc == self.averageLength - 1:
            self.learnt = True
        self.Loc = (self.Loc + 1)%self.averageLength
        #if self.Loc%32 == 1:
            #print ModuleName, "Av: ", av[0], av[1], av[2]

        if self.learnt:
            energy = (abs(accel[0])-abs(av[0])) + \
                     (abs(accel[1])-abs(av[1])) + \
                     (abs(accel[2])-abs(av[2]))
        else:
            energy = 0.0
        return energy

class App:
    """ This is what actually does the work """
    status = "ok"
    energyThreshold = 2.0
    def __init___(self):
        self.status = "ok"

    def processResp(self, resp):
        req = {}
        #print "response: ", resp
        if resp["name"] != "sensorTag":
            pass
        if resp["content"] == "accel":
            accel = [resp["data"]["x"], resp["data"]["y"], \
                    resp["data"]["z"]]
            #print ModuleName, "accel = ", accel
            energy = accel1.detectEvent(accel)
            if energy > self.energyThreshold:
                print ModuleName, "Energy = ", energy
                #processData(energy)
            req = {"id": id,
                   "req": "req-accel"}
        elif resp["content"] == "none" and resp["status"] == "ok":
            req = {"id": id,
                   "req": "req-accel"}
        else:
            req = {"id": id,
                   "req": "none"}
            # A problem has occured. Report it to bridge manager
            self.status = "adaptor problem"
        return req 

    def cbManagerMsg(self, cmd):
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

class cbAdaptorClient(LineReceiver):
    def connectionMade(self):
        req = {"id": id,
               "req": "init"}
        self.sendLine(json.dumps(req))

    def lineReceived(self, data):
        resp = json.loads(data)
        req = p.processResp(resp)
        self.sendLine(json.dumps(req))

class cbManagerClient(LineReceiver):
    def connectionMade(self):
        msg = {"id": id,
               "status": "hello"} 
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
        print "App improper usage"
        exit(1)
    
    managerSocket = sys.argv[1]
    adaptorSocket = sys.argv[2]
    
    p = App()
    accel1 = Accelerometer()
    sensorTagfactory = cbClientFactory()
    sensorTagfactory.protocol = cbAdaptorClient 
    reactor.connectUNIX(adaptorSocket, sensorTagfactory, timeout=10)
    managerFactory = cbClientFactory()
    managerFactory.protocol = cbManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    reactor.run()
    
