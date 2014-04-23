#!/usr/bin/env python
# eew_app.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "example" 

import sys
import os.path
import time
import logging
from cbcommslib import CbApp
from cbconfig import *

class DataManager:
    """ Managers data storage for all sensors """
    def __init__(self, cbSendMsg):
        self.cbSendMsg = cbSendMsg
        self.now = self.niceTime(time.time())
        self.cvsList = []
        self.cvsLine = []
        self.index = []

   def storeTemp(self, deviceID, timeStamp, temp):
        self.writeCVS(timeStamp)
        index = self.index.index(deviceID)
        self.cvsLine[index*self.numberServices + 0] = str("%2.1f" %temp)
        req = {
               "msg": "req",
               "verb": "post",
               "channel": self.appNum,
               "body": {
                        "msg": "data",
                        "appID": self.appID,
                        "deviceID": deviceID,
                        "type": "temperature",
                        "timeStamp": timeStamp,
                        "data": temp
                       }
              }
        self.cbSendMsg(req, "conc")

class TemperatureMeasure():
    """ Either send temp every minute or when it changes. """
    def __init__(self, id):
        # self.mode is either regular or on_change
        self.mode = "on_change"
        self.minChange = 0.2
        self.id = id
        epochTime = time.time()
        self.prevEpochMin = int(epochTime - epochTime%60)
        self.currentTemp = 0.0

    def processTemp (self, resp):
        timeStamp = resp["timeStamp"] 
        temp = resp["data"]
        if self.mode == "regular":
            epochMin = int(timeStamp - timeStamp%60)
            if epochMin != self.prevEpochMin:
                temp = resp["data"]
                self.dm.storeTemp(self.id, self.prevEpochMin, temp) 
                self.prevEpochMin = epochMin
        else:
            if abs(temp-self.currentTemp) >= TEMP_MIN_CHANGE:
                self.dm.storeTemp(self.id, timeStamp, temp) 
                self.currentTemp = temp

class App(CbApp):
    def __init__(self, argv):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        # The following 3 declarations must be made
        CbApp.processResp = self.processResp
        CbApp.cbAppConfigure = self.configure
        CbApp.processConcResp = self.processConcResp
        #
        self.appClass = "monitor"
        self.state = "stopped"
        self.status = "ok"
        self.devices = []
        self.devServices = [] 
        self.idToName = {} 
        self.temp = []
        #CbApp.__init__ MUST be called
        CbApp.__init__(self, argv)

    def states(self, action):
        if action == "clear_error":
            self.state = "running"
        else:
            self.state = action
        msg = {"id": self.id,
               "status": "state",
               "state": self.state}
        self.cbSendManagerMsg(msg)

    def processConcResp(self, resp):
        #logging.debug("%s resp from conc: %s", ModuleName, resp)
        if resp["resp"] == "config":
            msg = {
               "msg": "req",
               "verb": "post",
               "channel": int(self.id[3:]),
               "body": {
                        "msg": "services",
                        "appID": self.id,
                        "idToName": self.idToName,
                        "services": self.devServices
                       }
                  }
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
        #logging.debug("%s resp: %s", ModuleName, resp)
        elif resp["content"] == "temperature":
            for t in self.temp:
                if t.id == resp["id"]:
                    t.processTemp(resp)
                    break
        elif resp["content"] == "services":
            self.devServices.append(resp)
            serviceReq = []
            for p in resp["services"]:
                # Based on services offered & whether we want to enable them
                if p["parameter"] == "temperature":
                    if TEMP:
                        self.temp.append(TemperatureMeasure(resp["id"]))
                        self.temp[-1].dm = self.dm
                        serviceReq.append("temperature")
            msg = {"id": self.id,
                   "req": "services",
                   "services": serviceReq}
            self.cbSendMsg(msg, resp["id"])

    def configure(self, config):
        """ Config is based on what sensors are available """
        for adaptor in config["adts"]:
            adtID = adaptor["id"]
            if adtID not in self.devices:
                # Because configure may be re-called if devices are added
                name = adaptor["name"]
                friendly_name = adaptor["friendly_name"]
                logging.debug("%s Configure app. Adaptor name: %s", ModuleName, name)
                self.idToName[adtID] = friendly_name
                self.devices.append(adtID)
        self.states("starting")

if __name__ == '__main__':

    app = App(sys.argv)
