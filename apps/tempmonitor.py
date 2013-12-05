#!/usr/bin/env python
# tempmonitor.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Temp monitor        " 

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
        tempFile = "tempmon" + deviceID
        if os.path.isfile(tempFile):
            self.datFiles[deviceID]["temp"] = open(tempFile, "a+", 0)
        else:
            self.datFiles[deviceID]["temp"] = open(tempFile, "a+", 0)
            self.datFiles[deviceID]["temp"].write("epochTime,objT,ambT\n")

    def storeTemp(self, deviceID, epochMin, objT, ambT):
        dat = str(epochMin) + ", " + str("%5.1f" %objT) + ", " + \
            str("%5.1f" %ambT) + "\n"
        #print ModuleName, "temp ", deviceID, " ", dat
        self.datFiles[deviceID]["temp"].write(dat)

    def closeDB(self):
        # Close db cleanly when the app is closed
        pass
 
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
            for t in self.temp:
                #print ModuleName, "t.id = ", t.id, " resp id = ", resp["id"]
                if t.id == resp["id"]:
                    t.processTemp(resp)
                    #Dumb wait for 5 seconds for now
                    time.sleep(5)
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
                self.temp.append(TemperatureMeasure(adtID))
                self.temp[-1].dm = self.dm
                self.dm.initDevice(adtID)

if __name__ == '__main__':

    app = App(sys.argv)
