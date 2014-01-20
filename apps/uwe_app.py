#!/usr/bin/env python
# uwe_app.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "uwe_app             " 

import sys
import os.path
import time
from pprint import pprint
from cbcommslib import CbApp

class DataManager:
    """ Managers data storage for all sensors """
    def __init__(self, cbSendMsg):
        self.cbSendMsg = cbSendMsg
        self.datFiles = {}

    def initDevice(self, deviceID):
        print ModuleName, "initDevices, deviceID = ", deviceID
        #self.datFiles[deviceID] = {}
        #tempFile = deviceID + "temp"
        #if os.path.isfile(tempFile):
        #    self.datFiles[deviceID]["temp"] = open(deviceID + "temp", "a+", 0)
        #else:
        #    self.datFiles[deviceID]["temp"] = open(deviceID + "temp", "a+", 0)
        #    self.datFiles[deviceID]["temp"].write("epochTime,objT,ambT\n")
        #accelFile = deviceID + "accel"
        #if os.path.isfile(accelFile):
        #    self.datFiles[deviceID]["accel"] = open(deviceID + "accel", "a+", 0)
        #else:
        #    self.datFiles[deviceID]["accel"] = open(deviceID + "accel", "a+", 0)
        #    self.datFiles[deviceID]["accel"].write("epochTime,e0,e1,e2\n")

    def storeAccel(self, deviceID, timeStamp, a):
        #timeStamp = str(int(timeStamp*10)/10)
        #dat = str("%12.1f" %timeStamp) + ", " + str(a[0]) + ", " + str(a[1]) + \
        #    ", " + str(a[2]) + "\n" 
        #self.datFiles[deviceID]["accel"].write(dat)
        req = {
               "msg": "req",
               "req": "put",
               "appID": self.appID,
               "deviceID": deviceID,
               "timeStamp": timeStamp,
               "type": "accel",
               "data": a
              }
        self.cbSendMsg(req, "conc")

    def storeTemp(self, deviceID, timeStamp, temp):
        #dat = str(timeStamp) + ", " + str("%5.1f" %temp) + "\n"
        #self.datFiles[deviceID]["temp"].write(dat)
        req = {
               "msg": "req",
               "req": "put",
               "appID": self.appID,
               "deviceID": deviceID,
               "type": "temperature",
               "timeStamp": timeStamp,
               "data": temp
              }
        self.cbSendMsg(req, "conc")

    def storeIrTemp(self, deviceID, timeStamp, temp):
        req = {
               "msg": "req",
               "req": "put",
               "appID": self.appID,
               "deviceID": deviceID,
               "type": "ir_temperature",
               "timeStamp": timeStamp,
               "data": temp
              }
        self.cbSendMsg(req, "conc")

    def storeButtons(self, deviceID, timeStamp, buttons):
        req = {
               "msg": "req",
               "req": "put",
               "appID": self.appID,
               "deviceID": deviceID,
               "type": "buttons",
               "timeStamp": timeStamp,
               "data": buttons
              }
        self.cbSendMsg(req, "conc")

    def storeGyro(self, deviceID, timeStamp, gyro):
        req = {
               "msg": "req",
               "req": "put",
               "appID": self.appID,
               "deviceID": deviceID,
               "type": "gyro",
               "timeStamp": timeStamp,
               "data": gyro
              }
        self.cbSendMsg(req, "conc")

    def storeMagnet(self, deviceID, timeStamp, magnet):
        req = {
               "msg": "req",
               "req": "put",
               "appID": self.appID,
               "deviceID": deviceID,
               "type": "magnetometer",
               "timeStamp": timeStamp,
               "data": magnet
              }
        self.cbSendMsg(req, "conc")

class Accelerometer:
    def __init__(self, id):
        self.id = id

    def processAccel(self, resp):
        accel = [resp["data"]["x"], resp["data"]["y"], \
                resp["data"]["z"]]
        timeStamp = resp["timeStamp"]
        self.dm.storeAccel(self.id, timeStamp, accel) 
        #localTime = time.localtime(resp["accel"]["timeStamp"])
        #now = time.strftime("%H:%M:%S", localTime)
        #print ModuleName, self.id, now, " accel: ", accel
 
class TemperatureMeasure():
    # Commented-out lines send temperature every minute
    def __init__(self, id):
        self.id = id
        #epochTime = time.time()
        #self.prevEpochMin = int(epochTime - epochTime%60)
        #self.currentTemp = {"objT": 0, "ambT": 0}

    def processTemp (self, resp):
        timeStamp = resp["timeStamp"] 
        temp = resp["data"]
        #epochMin = int(timeStamp - timeStamp%60)
        #if epochMin != self.prevEpochMin:
            #temp = resp["data"]
            #self.currentTemp = {"temp": temp}
            #self.dm.storeTemp(self.id, self.prevEpochMin, temp) 
            #self.prevEpochMin = epochMin
        self.dm.storeTemp(self.id, timeStamp, temp) 

class IrTemperatureMeasure():
    # Commented-out lines send temperature every minute
    def __init__(self, id):
        self.id = id

    def processIrTemp (self, resp):
        timeStamp = resp["timeStamp"] 
        temp = resp["data"]
        self.dm.storeIrTemp(self.id, timeStamp, temp) 

class Buttons():
    def __init__(self, id):
        self.id = id

    def processButtons(self, resp):
        timeStamp = resp["timeStamp"] 
        buttons = resp["data"]
        self.dm.storeButtons(self.id, timeStamp, buttons)

class Gyro():
    def __init__(self, id):
        self.id = id

    def processGyro(self, resp):
        gyro = [resp["data"]["x"], resp["data"]["y"], \
                resp["data"]["z"]]
        timeStamp = resp["timeStamp"] 
        self.dm.storeGyro(self.id, timeStamp, gyro)

class Magnet():
    def __init__(self, id):
        self.id = id

    def processMagnet(self, resp):
        mag = [resp["data"]["x"], resp["data"]["y"], \
               resp["data"]["z"]]
        timeStamp = resp["timeStamp"] 
        self.dm.storeMagnet(self.id, timeStamp, mag)

class App(CbApp):
    def __init__(self, argv):
        # The following 3 declarations must be made
        self.appClass = "monitor"
        CbApp.processResp = self.processResp
        CbApp.cbAppConfigure = self.configure
        CbApp.processConcResp = self.processConcResp
        #
        self.accel = []
        self.gyro = []
        self.magnet = []
        self.temp = []
        self.irTemp = []
        self.buttons = []
        self.devices = []
        self.devServices = [] 
        self.idToName = {} 
        self.dm = DataManager(self.cbSendMsg)
        CbApp.__init__(self, argv)

    def processConcResp(self, resp):
        print ModuleName, "resp from conc = ", resp
        if resp["resp"] == "config":
            msg = {"appID": self.id,
                   "msg": "services",
                   "idToName": self.idToName,
                   "services": self.devServices}
            self.cbSendMsg(msg, "conc")
        else:
            msg = {"appID": self.id,
                   "msg": "error",
                   "message": "unrecognised response from concentrator"}
            self.cbSendMsg(msg, "conc")

    def processResp(self, resp):
        """
        This method is called in a thread by cbcommslib so it will not cause
        problems if it takes some time to complete (other than to itself).
        """
        #print ModuleName, "resp = ", resp
        if resp["content"] == "acceleration":
            for a in self.accel:
                if a.id == resp["id"]: 
                    a.processAccel(resp)
                    break
        elif resp["content"] == "temperature":
            for t in self.temp:
                if t.id == resp["id"]:
                    t.processTemp(resp)
                    break
        elif resp["content"] == "ir_temperature":
            for t in self.irTemp:
                if t.id == resp["id"]:
                    t.processIrTemp(resp)
                    break
        elif resp["content"] == "gyro":
            for g in self.gyro:
                if g.id == resp["id"]:
                    g.processGyro(resp)
                    break
        elif resp["content"] == "magnetometer":
            for g in self.magnet:
                if g.id == resp["id"]:
                    g.processMagnet(resp)
                    break
        elif resp["content"] == "buttons":
            for b in self.buttons:
                if b.id == resp["id"]:
                    b.processButtons(resp)
                    break
        elif resp["content"] == "services":
            self.devServices.append(resp)
            serviceReq = []
            for p in resp["services"]:
                if p["parameter"] == "temperature":
                    self.temp.append(TemperatureMeasure(resp["id"]))
                    self.temp[-1].dm = self.dm
                    serviceReq.append("temperature")
                if p["parameter"] == "ir_temperature":
                    self.irTemp.append(IrTemperatureMeasure(resp["id"]))
                    self.irTemp[-1].dm = self.dm
                    serviceReq.append("ir_temperature")
                elif p["parameter"] == "acceleration":
                    self.accel.append(Accelerometer(resp["id"]))
                    self.accel[-1].dm = self.dm
                    serviceReq.append("acceleration")
                elif p["parameter"] == "gyro":
                    self.gyro.append(Gyro(resp["id"]))
                    self.gyro[-1].dm = self.dm
                    serviceReq.append("gyro")
                elif p["parameter"] == "magnetometer":
                    self.magnet.append(Magnet(resp["id"]))
                    self.magnet[-1].dm = self.dm
                    serviceReq.append("magnetometer")
                elif p["parameter"] == "buttons":
                    self.buttons.append(Buttons(resp["id"]))
                    self.buttons[-1].dm = self.dm
                    serviceReq.append("buttons")
            self.dm.initDevice(resp["id"])
            msg = {"id": self.id,
                   "req": "services",
                   "services": serviceReq}
            self.cbSendMsg(msg, resp["id"])
        elif resp["content"] == "none":
            pass
        else:
            # A problem has occured. Report it to bridge manager
            #self.status = "adaptor problem"
            pass

    def configure(self, config):
        """ Config is based on what sensors are available """
        print ModuleName, "Configure app", self.id
        self.dm.appID = self.id
        for adaptor in config["adts"]:
            adtID = adaptor["id"]
            if adtID not in self.devices:
                # Because configure may be re-called if devices are added
                name = adaptor["name"]
                friendly_name = adaptor["friendly_name"]
                print ModuleName, "configure app, adaptor name = ", name
                self.idToName[adtID] = friendly_name
                self.devices.append(adtID)

if __name__ == '__main__':

    app = App(sys.argv)
