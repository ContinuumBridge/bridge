#!/usr/bin/env python
# sensortagadaptor4.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Test SensorTag      "

import pexpect
import sys
import time
import os
from cbcommslib import cbAdaptor
from threading import Thread

class Adaptor(cbAdaptor):
    def __init__(self, argv):
        #cbAdaptor methods processReq & cbAdtConfig MUST be subclassed
        cbAdaptor.processReq = self.processReq
        cbAdaptor.cbAdtConfigure = self.configure
        self.connected = False
        self.status = "ok"
        self.accel = {} #To hold latest accel values
        self.accelReady = {}
        self.startTime = time.time()
        self.tick = 0
        self.temp = {}  #To hold temperature values
        self.temp["ambT"] = 0
        self.temp["objT"] = 0
        self.temp["timeStamp"] = time.time()
        #cbAdaprot.__init__ MUST be called
        cbAdaptor.__init__(self, argv)

    def initSensorTag(self):
        print ModuleName, "initSensorTag", self.id, " - ", self.friendlyName
        self.connected = True
        return "ok"

    def startApp(self):
        """
        Continually attempts to connect to the device.
        Gating with doStop needed because adaptor may be stopped before
        the device is ever connected.
        """
        if self.connected == True:
            tagStatus = "Already connected" # Indicates app restarting
        while self.connected == False and not self.doStop:
            tagStatus = self.initSensorTag()    
            if tagStatus != "ok":
                print ModuleName
                print ModuleName, "ERROR. ", self.id, " - ", \
                    self.friendlyName, " failed to initialise"
                print ModuleName, "Please press side button"
                print ModuleName, \
                      "If problem persists SensorTag may be out of range"
        if not self.doStop:
            # Start a thread that continually gets accel and temp values
            t = Thread(target=self.getValues)
            t.start()
            print ModuleName, self.id, " - ", self.friendlyName, \
                "successfully initialised"
 
    def signExtend(self, a):
        if a > 127:
            a = a - 256
        return a

    def s16tofloat(self, s16):
        f = float.fromhex(s16)
        if f > 32767:
            f -= 65535
        return f

    def getValues(self):
        """Continuually updates accel and temp values.

        Run in a thread. When new accel values are received, the thread
        sets the accelReady flag for each attached app to True.  
        """
        while not self.doStop:
            time.sleep(0.33)
            self.tick += 1
            if self.tick == 56:
                # Enable temperature sensor every 30 seconds & take reading
                pass
                #self.gatt.sendline('char-write-cmd 0x26 0100')
            elif self.tick == 60:
                # Allow about a second before reading temperature
                self.tick = 0
                # Calculate temperatures
                self.temp["ambT"] = 33.3
                self.temp["objT"] = 22.2
                self.temp["timeStamp"] = time.time()
                #print ModuleName, "objT = ", objT, " ambT = ", ambT

            self.accel["x"] = 1.0
            self.accel["y"] = 2.0
            self.accel["z"] = 3.0
            self.accel["timeStamp"] = time.time()
            for a in self.accelReady:
                self.accelReady[a] = True

    def reqAccel(self, appID):
        """
        Ensures that a set of accel values are provided only once to an app.
        appID refers to the app that has requested the latest accel values.
        """
        while self.accelReady[appID] == False:
            #print ModuleName, "Waiting for accelReady"
            time.sleep(0.3) 
        accel = self.accel
        self.accelReady[appID] = False
        return accel 

    def reqTemp(self):
        return self.temp
    
    def processReq(self, req):
        """
        Processes requests from apps.
        Called in a thread and so it is OK if it blocks.
        Called separately for every app that can make requests.
        """
        #print ModuleName, "processReq req = ", req
        tagStatus = "ok"
        if req["req"] == "init" or req["req"] == "char":
           resp = {"name": self.name,
                    "id": self.id,
                    "status": tagStatus,
                    "capabilities": {"accelerometer": "0.1",
                                     "temperature": "5"},
                    "content": "none"}
        elif req["req"] == "req-data":
            resp = {"name": self.name,
                    "id": self.id,
                    "status": "ok",
                    "content": "data", 
                    "accel": self.reqAccel(req["id"]),
                    "temp": self.reqTemp()}
        else:
            resp = {"name": self.name,
                    "id": self.id,
                    "status": "bad-req",
                    "content": "none"}
        #print ModuleName, "resp = ", resp
        return resp

    def configure(self, config):
        """Config is based on what apps are to be connected."""
        for app in config["apps"]:
            self.accelReady[app["id"]] = False
        self.startApp()

if __name__ == '__main__':
    adaptor = Adaptor(sys.argv)
