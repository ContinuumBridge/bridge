#!/usr/bin/python
ModuleName = "Living              " 
id = "living"

import sys
import os.path
import time
import json
import anydbm
from pprint import pprint
from collections import defaultdict
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import reactor

class Accelerometer:
    """ Takes x, y, z accelerometer values & produces an energy output.
        The energy output is the deviation of the absolute values from
        a moving average that is calculated over the last averageLength
        samples. """

    averageLength = 128 
    Loc = 0
    total = [0.0, 0.0, 0.0]
    learnt = False
    values = []
    prevMinOfDay = 0
    startOfTime = True

    def __init__(self):
        for i in xrange(self.averageLength):
            self.values.append([0.0, 0.0, 0.0])
        self.livingData = self.dictTree()
        self.accelFile = open("l.csv", mode="w")

    def dictTree(self):
        return defaultdict(self.dictTree)

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
            energy = [(abs(accel[0])-abs(av[0])), \
                      (abs(accel[1])-abs(av[1])), \
                      (abs(accel[2])-abs(av[2]))]
        else:
            energy = [0.0, 0.0, 0.0]
        return energy

    def processAccel(self, resp):
        energyThreshold = 1.7
        accel = [resp["data"]["x"], resp["data"]["y"], \
                resp["data"]["z"]]
        energy = accel1.detectEvent(accel)
        now = time.ctime(resp["data"]["timeStamp"])
        trigger = False
        for e in range(3):
            if energy[e] > energyThreshold:
                trigger = True
                energy[e] = energy[e] - energyThreshold
            else:
                energy[e] = 0
        if trigger:
            now = time.ctime(resp["data"]["timeStamp"])
            print ModuleName, now, " Energy ", e, " = ", energy[e] 
            timeStamp = resp["data"]["timeStamp"] 
            minOfDay = int(timeStamp - timeStamp%60)
            if minOfDay != self.prevMinOfDay:
                print ModuleName, "New minOfDay = ", minOfDay
                for e in range(3):
                    self.livingData["dev1"][minOfDay][e] = int(energy[e] * 100)
                #dat = json.dumps(self.livingData)
                #pprint(dat)
                if self.prevMinOfDay != 0:
                    self.accelFile.write(time.ctime(self.prevMinOfDay) \
                         + ",  " \
                         + str(self.prevMinOfDay) + ",  " + \
                         str(self.livingData["dev1"][self.prevMinOfDay][0]) \
                         + ",  " + \
                         str(self.livingData["dev1"][self.prevMinOfDay][1]) \
                         + ",  " + \
                         str(self.livingData["dev1"][self.prevMinOfDay][2]) \
                         + "\r\n")
                self.prevMinOfDay = minOfDay
            else:       
                print ModuleName, "Same minOfDay as before = ", minOfDay
                for e in range(3):
                    self.livingData["dev1"][minOfDay][e] += \
                    int(energy[e] * 100)
 
class App:
    """ This is what actually does the work """
    status = "ok"
    def __init___(self):
        self.status = "ok"

    def processResp(self, resp):
        req = {}
        if resp["name"] != "sensorTag":
            pass
        if resp["content"] == "accel":
            accel1.processAccel(resp)
            req = {"id": id,
                   "req": "req-accel"}
        elif resp["content"] == "none":
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
    
