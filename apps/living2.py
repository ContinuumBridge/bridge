#!/usr/bin/python
ModuleName = "Living 2            " 
id = "living2"

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
            CREATE TABLE IF NOT EXISTS sensors(id INTEGER PRIMARY KEY, 
                       name TEXT,
                       epochTime INT, e0 INT, e1 INT, e2 INT, objT INT, 
                       ambT INT)
        ''')
        self.db.commit()
        reactor.callLater(60, self.dumpData)

    def storeAccel(self, thingName, epochMin, energy):
        print ModuleName, "storeAccel: ", thingName, epochMin, energy
        cursor = self.db.cursor()
        cursor.execute("SELECT rowid FROM sensors WHERE epochTime = ?", 
                       (epochMin,))
        data=cursor.fetchone()
        if data is None:
            print ModuleName, "storeAccel new epochMin"
            cursor.execute('''INSERT INTO sensors(name, epochTime, e0, e1, e2)
                      VALUES(?,?,?,?,?)''', 
                      (thingName, epochMin, energy[0], energy[1], energy[2]))
        else:
            print ModuleName, "storeAccel epochMin already exists"
            cursor.execute('''UPDATE sensors SET e0 = ? 
                      WHERE epochTime = ? ''', (energy[0], epochMin))
            cursor.execute('''UPDATE sensors SET e1 = ? 
                      WHERE epochTime = ? ''', (energy[1], epochMin))
            cursor.execute('''UPDATE sensors SET e2 = ? 
                      WHERE epochTime = ? ''', (energy[2], epochMin))
        self.db.commit()

    def storeTemp(self, thingName, epochMin, objT, ambT):
        print ModuleName, "storeTemp: ", thingName, epochMin, objT, ambT
        cursor = self.db.cursor()
        cursor.execute("SELECT rowid FROM sensors WHERE epochTime = ?", 
                       (epochMin,))
        data=cursor.fetchone()
        if data is None:
            print ModuleName, "storeTemp new epochMin"
            cursor.execute('''INSERT INTO sensors(name, epochTime, objT, ambT)
                      VALUES(?,?,?,?)''', 
                      (thingName, epochMin, objT, ambT))
        else:
            print ModuleName, "storeTemp epochMin already exists"
            cursor.execute('''UPDATE sensors SET objT = ? 
                      WHERE epochTime = ? ''', (objT, epochMin))
            cursor.execute('''UPDATE sensors SET ambT = ? 
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
                       FROM sensors''')
        all_rows = cursor.fetchall()
        for row in all_rows:
            print ModuleName, row[0], ": ", row[1], "  ", row[2], "  ", \
                row[3], "  ", row[4], "  ", row[5] 
        reactor.callLater(60, self.dumpData)

    def closeDB(self):
        # Close db cleanly when the app is closed
        self.db.close()
 
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
    prevEpochMin = 0
    energySum = [0, 0, 0] 

    def __init__(self, name):
        self.name = name
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
            energy = [(abs(accel[0])-abs(av[0])), \
                      (abs(accel[1])-abs(av[1])), \
                      (abs(accel[2])-abs(av[2]))]
        else:
            energy = [0.0, 0.0, 0.0]
        return energy

    def processAccel(self, resp):
        energyThreshold = 1.7
        accel = [resp["accel"]["x"], resp["accel"]["y"], \
                resp["accel"]["z"]]
        energy = accel1.detectEvent(accel)
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
                    dm.storeAccel(self.name, self.prevEpochMin, self.energySum) 
                self.prevEpochMin = epochMin
            else:       
                #print ModuleName, "Same epochMin as before = ", epochMin
                for e in range(3):
                    self.energySum[e] += int(energy[e] * 100)
 
class TemperatureMeasure():

    def __init__(self, name):
        self.name = name
        self.prevEpochMin = time.time()

    def processTemp (self, resp):
        timeStamp = resp["temp"]["timeStamp"] 
        epochMin = int(timeStamp - timeStamp%60)
        if epochMin != self.prevEpochMin:
            objT = resp["temp"]["objT"]
            ambT = resp["temp"]["ambT"] 
            dm.storeTemp(self.name, self.prevEpochMin, objT, ambT) 
            self.prevEpochMin = epochMin
            now = time.ctime(resp["temp"]["timeStamp"])
            print ModuleName, now, " ObjT = ", objT, " AmbT = ", ambT

class App:
    """ This is what actually does the work """
    status = "ok"
    lastTempTime = 0.0
    def __init___(self):
        self.status = "ok"

    def processResp(self, resp):
        req = {}
        if resp["name"] != "sensorTag":
            pass
        if resp["content"] == "data":
            accel1.processAccel(resp)
            temp1.processTemp(resp)
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
        pass

    def cbManagerMsg(self, cmd):
        #print ModuleName, "Received from manager: ", cmd
        if cmd["cmd"] == "stop":
            print ModuleName, "Stopping"
            dm.closeDB()
            msg = {"id": id,
                   "status": "stopping"}
            time.sleep(1)
            reactor.stop()
            sys.exit
        elif cmd["cmd"] == "config":
            self.configure(cmd["config"]) 
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
    accel1 = Accelerometer("tag1")
    temp1 = TemperatureMeasure("tag1")
    dm = DataManager()
    sensorTagfactory = cbClientFactory()
    sensorTagfactory.protocol = cbAdaptorClient 
    reactor.connectUNIX(adaptorSocket, sensorTagfactory, timeout=10)
    managerFactory = cbClientFactory()
    managerFactory.protocol = cbManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    reactor.run()
    
