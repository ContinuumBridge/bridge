#!/usr/bin/env python
# living6.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Living 6            " 

import sys
import os.path
import time
from pprint import pprint
from cbcommslib import cbApp

class DataManager:
    """ Managers data storage for all sensors """
    def __init__(self):
        self.datFiles = {}

    def initDevice(self, deviceID):
        print ModuleName, "initDevices, deviceID = ", deviceID
        self.datFiles[deviceID] = {}
        tempFile = deviceID + "temp"
        if os.path.isfile(tempFile):
            self.datFiles[deviceID]["temp"] = open(deviceID + "temp", "a+", 0)
        else:
            self.datFiles[deviceID]["temp"] = open(deviceID + "temp", "a+", 0)
            self.datFiles[deviceID]["temp"].write("epochTime,objT,ambT\n")
        accelFile = deviceID + "accel"
        if os.path.isfile(accelFile):
            self.datFiles[deviceID]["accel"] = open(deviceID + "accel", "a+", 0)
        else:
            self.datFiles[deviceID]["accel"] = open(deviceID + "accel", "a+", 0)
            self.datFiles[deviceID]["accel"].write("epochTime,e0,e1,e2\n")

    def storeAccel(self, deviceID, epochSec, e):
        #timeStamp = str(int(epochSec*10)/10)
        dat = str("%12.1f" %epochSec) + ", " + str(e[0]) + ", " + str(e[1]) + \
            ", " + str(e[2]) + "\n" 
        self.datFiles[deviceID]["accel"].write(dat)

    def storeTemp(self, deviceID, epochMin, objT, ambT):
        dat = str(epochMin) + ", " + str("%5.1f" %objT) + ", " + \
            str("%5.1f" %ambT) + "\n"
        self.datFiles[deviceID]["temp"].write(dat)

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
        energyThreshold = 2.5
        self.accel = [resp["accel"]["x"], resp["accel"]["y"], \
                resp["accel"]["z"]]
        timeStamp = resp["accel"]["timeStamp"]
        energy = self.detectEvent(self.accel)
        for e in range(3):
            if energy[e] > energyThreshold:
                self.dm.storeAccel(self.id, timeStamp, energy) 
                #now = time.ctime(resp["accel"]["timeStamp"])
                localTime = time.localtime(resp["accel"]["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                print ModuleName, self.id, now, " event: ", energy
                break
 
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
            self.dm.storeTemp(self.id, self.prevEpochMin, objT, ambT) 
            self.prevEpochMin = epochMin

class App(cbApp):
    def __init__(self, argv):
        cbApp.processResp = self.processResp
        cbApp.cbAppConfigure = self.configure
        self.accel = []
        self.temp = []
        self.dm = DataManager()
        cbApp.__init__(self, argv)

    def processResp(self, resp):
        """
        Processes the response received from an adaptor & sends another req.

        This method is called in a thread by cbcommslib so it will not cause
        problems if it takes some time to complete (other than to itself).
        """
        req = {}
        #print ModuleName, "resp = ", resp
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
            req = {"id": self.id,
                   "req": "req-data"}
        elif resp["content"] == "none":
            req = {"id": self.id,
                   "req": "req-data"}
        else:
            req = {"id": self.id,
                   "req": "req-data"}
            # A problem has occured. Report it to bridge manager
            self.status = "adaptor problem"
        return req 

    def configure(self, config):
        """ Config is based on what sensors are available """
        print ModuleName, "Configure app"
        for adaptor in config["adts"]:
            name = adaptor["name"]
            adtID = adaptor["id"]
            print ModuleName, "configure app, adaptor name = ", name
            if name == "CB SensorTag Adt":
                self.accel.append(Accelerometer(adtID))
                self.accel[-1].dm = self.dm
                self.temp.append(TemperatureMeasure(adtID))
                self.temp[-1].dm = self.dm
                self.dm.initDevice(adtID)

if __name__ == '__main__':

    app = App(sys.argv)
