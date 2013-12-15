#!/usr/bin/env python
# living6.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Living 7            " 

import sys
import os.path
import time
from pprint import pprint
from cbcommslib import cbApp
from cbcommslib import cbConcClient

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
        """
        req = {
               "req": "put",
               "appID": self.appID,
               "deviceID": deviceID,
               "type": "accel",
               "data": {
                        "epochTime": epochSec,
                        "accel": e
                       }
              }
        self.sendConcReq(req)
        """

    def storeTemp(self, deviceID, epochMin, objT, ambT):
        dat = str(epochMin) + ", " + str("%5.1f" %objT) + ", " + \
            str("%5.1f" %ambT) + "\n"
        self.datFiles[deviceID]["temp"].write(dat)
        req = {
               "req": "put",
               "appID": self.appID,
               "deviceID": deviceID,
               "type": "temp",
               "data": {
                        "epochTime": epochMin,
                        "objT": objT,
                        "ambT": ambT
                       }
              }
        self.sendConcReq(req)

    def closeDB(self):
        # Close db cleanly when the app is closed
        pass
 
class Accelerometer:
    def __init__(self, id):
        self.id = id

    def processAccel(self, resp):
        accel = [resp["accel"]["x"], resp["accel"]["y"], \
                resp["accel"]["z"]]
        timeStamp = resp["accel"]["timeStamp"]
        self.dm.storeAccel(self.id, timeStamp, accel) 
        #localTime = time.localtime(resp["accel"]["timeStamp"])
        #now = time.strftime("%H:%M:%S", localTime)
        #print ModuleName, self.id, now, " accel: ", accel
 
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
        self.devices = []
        self.dm = DataManager()
        self.dm.sendConcReq = self.sendConcReq
        cbApp.__init__(self, argv)

    def processResp(self, resp):
        """
        Processes the response received from an adaptor & sends another req.

        This method is called in a thread by cbcommslib so it will not cause
        problems if it takes some time to complete (other than to itself).
        """
        req = {}
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
        self.dm.appID = self.id
        nameToID = []
        for adaptor in config["adts"]:
            name = adaptor["name"]
            friendlyName = adaptor["friendlyName"]
            adtID = adaptor["id"]
            print ModuleName, "configure app, adaptor name = ", name
            if name == "CB SensorTag Adt":
                self.accel.append(Accelerometer(adtID))
                self.accel[-1].dm = self.dm
                self.temp.append(TemperatureMeasure(adtID))
                self.temp[-1].dm = self.dm
                self.dm.initDevice(adtID)
                self.devices.append(adtID)
                nameToID.append({friendlyName: adtID})
        req = {
               "req": "init",
               "name": "living",
               "appID": self.id,
               "devices": self.devices,
               "nameToID": nameToID
              }
        self.sendConcReq(req)

if __name__ == '__main__':

    app = App(sys.argv)
