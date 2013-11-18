#!/usr/bin/python
ModuleName = "Living 3            " 

import sys
import os.path
import time
import json
import sqlite3
#import dataset
from pprint import pprint
from collections import defaultdict
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import reactor

class DataManager:
    """ Managers data storage for all sensors """
    def __init__(self):
        self.db = sqlite3.connect('living.db')
        cursor = self.db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS devData(id INTEGER PRIMARY KEY, 
               epochTime INT, 
               dev1E0 INT, dev1E1 INT, dev1E2 INT, dev1ObjT INT, dev1AmbT INT,
               dev2E0 INT, dev2E1 INT, dev2E2 INT, dev2ObjT INT, dev2AmbT INT,
               dev3E0 INT, dev3E1 INT, dev3E2 INT, dev3ObjT INT, dev3AmbT INT,
               dev4E0 INT, dev4E1 INT, dev4E2 INT, dev4ObjT INT, dev4AmbT INT)
        ''')
        self.db.commit()
#        dumpdata = task.LoopingCall(self.dumpData)
#        dumpdata.start(60) # call every minute

    def initDevice(self, deviceID):
        print ModuleName, "initDevices, deviceID = ", deviceID
        self.devs = {}
        try:
            with open('living.dev', 'r+') as devFile:
                self.devs = json.load(devFile)
                devFile.close()
                print ModuleName, "File exists, ", deviceID
                if not self.devs.has_key(deviceID):
                    numDevs = len(self.devs)
                    self.devs[deviceID] = "dev" + str(numDevs + 1)
                    with open('living.dev', 'w') as devFile:
                        json.dump(self.devs, devFile)
                        devFile.close()
        except:
            with open('living.dev', 'w') as devFile:
                self.devs[deviceID] = "dev1"
                json.dump(self.devs, devFile)
                devFile.close()
        print ModuleName, "self.devs: ", self.devs

    def storeAccel(self, deviceName, epochMin, energy):
        print ModuleName, "storeAccel: ", deviceName, epochMin, energy
        cursor = self.db.cursor()
        cursor.execute("SELECT rowid FROM devData WHERE epochTime = ?", 
                       (epochMin,))
        data=cursor.fetchone()
        if data is None:
            #print ModuleName, "storeAccel new epochMin"
            if self.devs[deviceName] == "dev1":
                cursor.execute('''INSERT INTO devData
                      (epochTime, dev1E0, dev1E1, dev1E2)
                      VALUES(?,?,?,?)''', 
                      (epochMin, energy[0], energy[1], energy[2]))
            elif self.devs[deviceName] == "dev2":
                cursor.execute('''INSERT INTO devData
                      (epochTime, dev2E0, dev2E1, dev2E2)
                      VALUES(?,?,?,?)''', 
                      (epochMin, energy[0], energy[1], energy[2]))
            else:
                print ModuleName, "Error. DB Unrecognised device ", deviceName
        else:
            #print ModuleName, "storeAccel epochMin already exists"
            if self.devs[deviceName] == "dev1":
                cursor.execute('''UPDATE devData SET dev1E0 = ? 
                          WHERE epochTime = ? ''', (energy[0], epochMin))
                cursor.execute('''UPDATE devData SET dev1E1 = ? 
                          WHERE epochTime = ? ''', (energy[1], epochMin))
                cursor.execute('''UPDATE devData SET dev1E2 = ? 
                          WHERE epochTime = ? ''', (energy[2], epochMin))
            elif self.devs[deviceName] == "dev2":
                cursor.execute('''UPDATE devData SET dev2E0 = ? 
                          WHERE epochTime = ? ''', (energy[0], epochMin))
                cursor.execute('''UPDATE devData SET dev2E1 = ? 
                          WHERE epochTime = ? ''', (energy[1], epochMin))
                cursor.execute('''UPDATE devData SET dev2E2 = ? 
                          WHERE epochTime = ? ''', (energy[2], epochMin))
            else:
                print ModuleName, "Error. DB Unrecognised device ", deviceName
        self.db.commit()

    def storeTemp(self, deviceName, epochMin, objT, ambT):
        print ModuleName, "storeTemp: ", deviceName, epochMin, objT, ambT
        cursor = self.db.cursor()
        cursor.execute("SELECT rowid FROM devData WHERE epochTime = ?", 
                       (epochMin,))
        data=cursor.fetchone()
        if data is None:
            #print ModuleName, "storeTemp new epochMin"
            if self.devs[deviceName] == "dev1":
                cursor.execute('''INSERT INTO devData(
                          epochTime, dev1ObjT, dev1AmbT)
                          VALUES(?,?,?)''', 
                          (epochMin, objT, ambT))
            elif self.devs[deviceName] == "dev2":
                cursor.execute('''INSERT INTO devData(
                          epochTime, dev2ObjT, dev2AmbT)
                          VALUES(?,?,?)''', 
                          (epochMin, objT, ambT))
        else:
            #print ModuleName, "storeTemp epochMin already exists"
            if self.devs[deviceName] == "dev1":
                cursor.execute('''UPDATE devData SET dev1ObjT = ? 
                          WHERE epochTime = ? ''', (objT, epochMin))
                cursor.execute('''UPDATE devData SET dev1AmbT = ? 
                          WHERE epochTime = ? ''', (ambT, epochMin))
            elif self.devs[deviceName] == "dev2":
                cursor.execute('''UPDATE devData SET dev2ObjT = ? 
                          WHERE epochTime = ? ''', (objT, epochMin))
                cursor.execute('''UPDATE devData SET dev2AmbT = ? 
                          WHERE epochTime = ? ''', (ambT, epochMin))
        self.db.commit()

#    def dumpThread(self):
#        with open('living.json', 'w') as datFile:
#            json.dump(self.livingData, datFile)

    def dumpData(self):
        print ModuleName, "Dumping data file"
#        d = threads.deferToThread(self.dumpThread())
        cursor = self.db.cursor()
        cursor.execute('''SELECT epochTime, e0, e1, e2, objT, ambT 
                       FROM devData''')
        all_rows = cursor.fetchall()
        for row in all_rows:
            print ModuleName, "tag1 ", row[0], ": ", row[1], "  ", row[2], "  ", \
                row[3], "  ", row[4], "  ", row[5] 
        cursor.execute('''SELECT epochTime, e0, e1, e2, objT, ambT 
                       FROM devData''')
        all_rows = cursor.fetchall()
        for row in all_rows:
            print ModuleName, "tag1 ", row[0], ": ", row[1], "  ", row[2], "  ", \
                row[3], "  ", row[4], "  ", row[5] 

    def closeDB(self):
        # Close db cleanly when the app is closed
        self.db.close()
 
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
        if self.Loc%32 == 1:
            print ModuleName, self.id,  " Av: ", "%7.3f" \
                  % self.av[0], "%7.3f" % self.av[1], "%7.3f" % self.av[2]

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
        self.prevEpochMin = time.time()
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
            print ModuleName, now, "  ", self.id, " ObjT = ", objT, \
                " AmbT = ", ambT

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
            purpose = adaptor["purpose"]
            self.friendlyLookup.update({id: friendlyName})
            self.adtInstances.append(id)
            if name == "SensorTag":
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
        reactor.callLater(30, self.monitorApp)

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

    livingFactory = LivingFactory()
    livingFactory.protocol = LivingProtocol
    reactor.connectTCP("localhost", 3123, livingFactory, timeout=10)
    
    managerSocket = sys.argv[1]
    id = sys.argv[2]
    
    p = App()
    dm = DataManager()
    managerFactory = cbClientFactory()
    managerFactory.protocol = cbManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    reactor.run()
