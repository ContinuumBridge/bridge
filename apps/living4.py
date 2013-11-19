#!/usr/bin/python
ModuleName = "Living 4            " 

import sys
import os.path
import time
import json
import sqlite3
import dataset
from pprint import pprint
from collections import defaultdict
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import reactor

class DataManager:
    """ Managers data storage for all sensors """
    tables = {} 
    def __init__(self):
        self.db = dataset.connect('sqlite:///living2.db')
        #self.firstDump = True
        #dumpdata = task.LoopingCall(self.dumpData)
        #dumpdata.start(90) # call every 90 seconds

    def initDevice(self, deviceID):
        print ModuleName, "initDevices, deviceID = ", deviceID
        self.tables[deviceID] = self.db[deviceID]

    def storeAccel(self, deviceName, epochMin, energy):
        now = time.strftime("%a %d %H:%M", time.localtime(epochMin))
        print ModuleName, deviceName, now, " accel: ",  energy
        data = {"epochTime": epochMin,
                "e0": energy[0],
                "e1": energy[1],
                "e2": energy[2]
               }
        row = self.tables[deviceName].find_one(epochTime=epochMin)
        if row is None:
            self.tables[deviceName].insert(data)
        else:
            self.tables[deviceName].upsert(data, ["epochTime"])

    def storeTemp(self, deviceName, epochMin, objT, ambT):
        now = time.strftime("%a %d %H:%M", time.localtime(epochMin))
        print ModuleName, deviceName, now, " temp: ", \
            "obj: %4.1f" % objT, "amb: %4.1f" % ambT
        data = {"epochTime": epochMin,
                "objT": objT,
                "ambT": ambT
               }
        row = self.tables[deviceName].find_one(epochTime=epochMin)
        if row is None:
            self.tables[deviceName].insert(data)
        else:
            self.tables[deviceName].upsert(data, ["epochTime"])

#    def dumpThread(self):
#        with open('living.json', 'w') as datFile:
#            json.dump(self.livingData, datFile)

    def dumpData(self):
        if not self.firstDump:
            print ModuleName, "Dumping data file"
#            d = threads.deferToThread(self.dumpThread())
            for dev in self.tables["tag1"]:
                print "tag1: ", dev["epochTime"], dev["e0"], dev["e1"], \
                      dev["e2"], dev["ambT"], dev["objT"]
            for dev in self.tables["tag2"]:
                print "tag2: ", dev["epochTime"], dev["e0"], dev["e1"], \
                      dev["e2"], dev["ambT"], dev["objT"]
        else:
             self.firstDump = False

    def closeDB(self):
        # Close db cleanly when the app is closed
        pass
 
class Accelerometer:
    """ Takes x, y, z accelerometer values & produces an energy output.
        The energy output is the deviation of the absolute values from
        a moving average that is calculated over the last averageLength
        samples. """

    averageLength = 128 

    def __init__(self, id):
        self.Loc = 0
        self.accel = []
        self.total = [0.0, 0.0, 0.0]
        self.learnt = False
        self.av = [0.0, 0.0, 0.0]
        self.prevEpochMin = 0
        self.energySum = [0, 0, 0] 
        self.event = False
        self.eventEnergy = 0
        self.id = id
        self.values = []
        for i in xrange(self.averageLength):
            self.values.append([0.0, 0.0, 0.0])

    def detectEvent(self, accel):
        """ Compute moving averages for x, y and z over averageLen samples """
        for i in xrange(3):
            self.total[i] = self.total[i] - self.values[self.Loc][i] + accel[i]
            self.values[self.Loc][i] = accel[i]
            self.av[i] = self.total[i]/self.averageLength
        if self.Loc == self.averageLength - 1:
            self.learnt = True
        self.Loc = (self.Loc + 1)%self.averageLength
        #if self.Loc%32 == 1:
            #print ModuleName, self.id,  " Av: ", "%7.3f" \
                  #% self.av[0], "%7.3f" % self.av[1], "%7.3f" % self.av[2]

        if self.learnt:
            energy = [(abs(accel[0])-abs(self.av[0])), \
                      (abs(accel[1])-abs(self.av[1])), \
                      (abs(accel[2])-abs(self.av[2]))]
        else:
            energy = [0.0, 0.0, 0.0]
        return energy

    def processAccel(self, resp):
        energyThreshold = 1.7
        self.accel = [resp["accel"]["x"], resp["accel"]["y"], \
                resp["accel"]["z"]]
        energy = self.detectEvent(self.accel)
        now = time.ctime(resp["accel"]["timeStamp"])
        trigger = False
        for e in range(3):
            if energy[e] > energyThreshold:
                trigger = True
                energy[e] = energy[e] - energyThreshold
            else:
                energy[e] = 0
        if trigger:
            now = time.ctime(resp["accel"]["timeStamp"])
            #print ModuleName, now, " Energy ", e, " = ", energy[e] 
            timeStamp = resp["accel"]["timeStamp"] 
            epochMin = int(timeStamp - timeStamp%60)
            if epochMin != self.prevEpochMin:
                #print ModuleName, "New epochMin = ", epochMin
                for e in range(3):
                    self.energySum[e] = int(energy[e] * 100)
                if self.prevEpochMin != 0:
                    dm.storeAccel(self.id, self.prevEpochMin, self.energySum) 
                self.prevEpochMin = epochMin
            else:       
                #print ModuleName, "Same epochMin as before = ", epochMin
                for e in range(3):
                    self.energySum[e] += int(energy[e] * 100)
            self.eventEnergy = 0
            for e in range(3):
                self.eventEnergy += int(energy[e] * 100)
            if self.eventEnergy > 40:
                #print ModuleName, "Event: ", self.id, eventEnergy, energy
                self.event = True
                self.eventData = self.eventEnergy
 
class TemperatureMeasure():

    def __init__(self, id):
        self.id = id
        epochTime = time.time()
        self.prevEpochMin = int(epochTime - epochTime%60)
        self.currentTemp = {"objT": 0, "ambT": 0}

    def processTemp (self, resp):
        timeStamp = resp["temp"]["timeStamp"] 
        epochMin = int(timeStamp - timeStamp%60)
        if epochMin != self.prevEpochMin:
            objT = resp["temp"]["objT"]
            ambT = resp["temp"]["ambT"] 
            self.currentTemp = {"objT": objT, "ambT": ambT}
            dm.storeTemp(self.id, self.prevEpochMin, objT, ambT) 
            self.prevEpochMin = epochMin
            now = time.ctime(resp["temp"]["timeStamp"])

class App:
    """ This is what actually does the work """
    status = "ok"
    doStop = False
    lastTempTime = 0.0
    friendlyLookup = {}
    accel = []
    temp = []
    cbFactory = []
    adtInstances = []
 
    def __init___(self):
        self.status = "ok"
        self.doStop = False

    def processResp(self, resp):
        req = {}
        #print ModuleName, "Response received: ", resp
        if resp["content"] == "data":
            for a in self.accel:
                if a.id == resp["id"]: 
                    a.processAccel(resp)
                    break
            for t in self.temp:
                #print ModuleName, "t.id = ", t.id, " resp id = ", resp["id"]
                if t.id == resp["id"]:
                    t.processTemp(resp)
                    break
            req = {"id": id,
                   "req": "req-data"}
        elif resp["content"] == "none":
            req = {"id": id,
                   "req": "req-data"}
        else:
            req = {"id": id,
                   "req": "req-data"}
            # A problem has occured. Report it to bridge manager
            self.status = "adaptor problem"
        return req 

    def configure(self, config):
        """ Config is based on what sensors are available """
        print ModuleName, "configure: ", config
        for adaptor in config["adts"]:
            name = adaptor["name"]
            id = adaptor["id"]
            adtSoc = adaptor["adtSoc"]
            friendlyName = adaptor["friendlyName"]
            #purpose = adaptor["purpose"]
            self.friendlyLookup.update({id: friendlyName})
            self.adtInstances.append(id)
            print ModuleName, "configure, adaptor name = ", name
            if name == "CB SensorTag Adt":
                self.accel.append(Accelerometer(id))
                self.temp.append(TemperatureMeasure(id))
                dm.initDevice(id)
            self.cbFactory.append(cbClientFactory())
            self.cbFactory[-1].protocol = cbAdaptorClient 
            reactor.connectUNIX(adtSoc, self.cbFactory[-1], timeout=10)

    def cbManagerMsg(self, cmd):
        #print ModuleName, "Received from manager: ", cmd
        if cmd["cmd"] == "stop":
            print ModuleName, "Stopping"
            self.doStop = True
            dm.closeDB()
            msg = {"id": id,
                   "status": "stopping"}
            time.sleep(2)
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
            msg = {"status": "none"}
        return msg

    def getAppTemp(self):
        msg = {}
        for t in self.temp:
            msg.update({t.id: t.currentTemp})
        return msg
 
    def getAppEvents(self):
        msg = {}
        for a in self.accel:
            if a.event:
                msg.update({a.id: a.eventData}),
            a.event = False 
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
               "class": "app",
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

class LivingProtocol(LineReceiver):
    def connectionMade(self):
        msg = {"id": id,
               "status": "ready"}
        self.sendLine(json.dumps(msg))
        #reactor.callLater(30, self.monitorApp)

    def lineReceived(self, line):
        print ModuleName, line

    def monitorApp(self):
        temp = p.getAppTemp()
        #print ModuleName, "temp = ", temp
        msg = {}
        for t in temp:
            msg.update({t: {"objT": temp[t]["objT"],
                            "ambT": temp[t]["ambT"],
                            "friendlyName": p.friendlyLookup[t]}}),

        ev = p.getAppEvents()
        for a in ev:
            friendlyName = p.friendlyLookup[a]
            energy = ev[a]
            msg.update({"event": {"name": friendlyName,
                                  "energy": energy}})
        #print ModuleName, "Monitor message: ", msg
        self.sendLine(json.dumps(msg))
        if not p.doStop:
            reactor.callLater(1, self.monitorApp)

class LivingFactory(ReconnectingClientFactory):
    """ Tries to reconnect to socket if connection lost """
    def clientConnectionFailed(self, connector, reason):
        print ModuleName, "Failed to connect to concentrator"
        print ModuleName,  reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        print ModuleName, "Connection to concentrator lost"
        print ModuleName, reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

if __name__ == '__main__':

    print ModuleName, "Hello"
    if len(sys.argv) < 3:
        print "App improper usage"
        exit(1)

    managerSocket = sys.argv[1]
    id = sys.argv[2]
    
    p = App()
    dm = DataManager()
    managerFactory = cbClientFactory()
    managerFactory.protocol = cbManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    reactor.run()
