#!/usr/bin/env python
# sensortagadaptor5.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "SensorTag 5         "

import pexpect
import sys
import time
import os
from cbcommslib import CbAdaptor
from threading import Thread

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        #CbAdaptor methods processReq & cbAdtConfig MUST be subclassed
        CbAdaptor.processReq = self.processReq
        CbAdaptor.cbAdtConfigure = self.configure
        self.connected = False  # Indicates we are connected to SensorTag
        self.configured = False # Indicates that adt has been configured
        self.status = "ok"
        self.tempApps = []
        self.irTempApps = []
        self.accelApps = []
        self.humidApps = []
        self.buttonApps = []
        #CbAdaprot.__init__ MUST be called
        CbAdaptor.__init__(self, argv)

    def initSensorTag(self):
        print ModuleName, "initSensorTag", self.id, " - ", self.friendlyName
        try:
            cmd = 'gatttool -i ' + self.device + ' -b ' + self.addr + \
                  ' --interactive'
            self.gatt = pexpect.spawn(cmd)
        except:
            print ModuleName, "dead"
            self.connected = False
            return "noConnect"
        self.gatt.expect('\[LE\]>')
        self.gatt.sendline('connect')
        self.gatt.expect('\[LE\]>', timeout=5)
        index = self.gatt.expect(['successful', pexpect.TIMEOUT], timeout=5)
        if index == 1:
            print ModuleName, "Connection to device timed out for", self.id, \
                " - ", self.friendlyName
            self.gatt.kill(9)
            return "timeout"
        else:
            print ModuleName, self.id, " - ", self.friendlyName, " connected"
            # Enable accelerometer
            self.gatt.sendline('char-write-cmd 0x31 01')
            self.gatt.expect('\[LE\]>')
            self.gatt.sendline('char-write-cmd 0x2e 0100')
            self.gatt.expect('\[LE\]>')
            # Period = 0x34 value x 10 ms (thought to be 0x0a)
            # Was running with 0x0A = 100 ms, now 0x22 = 500 ms
            self.gatt.sendline('char-write-cmd 0x34 22')
            self.gatt.expect('\[LE\]>')

            # Enable temperature sensors with notification
            self.gatt.sendline('char-write-cmd 0x29 01')
            self.gatt.expect('\[LE\]>')
            self.gatt.sendline('char-write-cmd 0x26 0100')
            self.gatt.expect('\[LE\]>')

            # Enable humidity sensor with notification
            self.gatt.sendline('char-write-cmd 0x3C 01')
            self.gatt.expect('\[LE\]>')
            self.gatt.sendline('char-write-cmd 0x39 0100')
            self.gatt.expect('\[LE\]>')
 
            # Enable button-press notification
            self.gatt.sendline('char-write-cmd 0x60 0100')
            self.gatt.expect('\[LE\]>')
            # We're connected!
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
 
    def s16tofloat(self, s16):
        f = float.fromhex(s16)
        if f > 32767:
            f -= 65535
        return f

    def s8tofloat(self, s8):
        f = float.fromhex(s8)
        if f > 127:
            f -= 256 
        return f

    def calcTemperature(self, raw):
        # Calculate temperatures
        objT = self.s16tofloat(raw[2] + \
                            raw[1]) * 0.00000015625
        ambT = self.s16tofloat(raw[4] + raw[3]) / 128.0
        Tdie2 = ambT + 273.15
        S0 = 6.4E-14
        a1 = 1.75E-3
        a2 = -1.678E-5
        b0 = -2.94E-5
        b1 = -5.7E-7
        b2 = 4.63E-9
        c2 = 13.4
        Tref = 298.15
        S = S0 * (1 + a1 * (Tdie2 - Tref) + \
            a2 * pow((Tdie2 - Tref), 2))
        Vos = b0 + b1 * (Tdie2 - Tref) + b2 * pow((Tdie2 - Tref), 2)
        fObj = (objT - Vos) + c2 * pow((objT - Vos), 2)
        objT = pow(pow(Tdie2,4) + (fObj/S), .25)
        objT -= 273.15
        #print ModuleName, "objT = ", objT, " ambT = ", ambT
        return objT, ambT

    def calcHumidity(self, raw):
        t1 = self.s16tofloat(raw[2] + raw[1])
        temp = -46.85 + 175.72/65536 * t1
        rawH = int((raw[4] + raw[3]), 16) & 0xFFFC # Clear bits [1:0] - status
        # Calculate relative humidity [%RH] 
        v = -6.0 + 125.0/65536 * float(rawH) # RH= -6 + 125 * SRH/2^16
        return v

    def getValues(self):
        """Continually updates accel and temp values.

        Run in a thread. When new accel values are received, the thread
        sets the accelReady flag for each attached app to True.  
        """
        while not self.doStop:
            index = self.gatt.expect(['value:.*', pexpect.TIMEOUT], timeout=10)
            if index == 1:
                # A timeout error. Attempt to restart the SensorTag
                status = ""
                while status != "ok" and not self.doStop:
                    print ModuleName, self.id, " - ", self.friendlyName, \
                        " gatt timeout"
                    self.gatt.kill(9)
                    time.sleep(1)
                    status = self.initSensorTag()   
                    print ModuleName, self.id, " - ", self.friendlyName, \
                        " re-init status = ", status
            else:
                type = self.gatt.before.split()
                raw = self.gatt.after.split()
                #print ModuleName, "type from SensorTag = ", type[3] 
                #print ModuleName, "raw from SensorTag = ", raw
                if type[3].startswith("0x002d"): 
                    # Accelerometer descriptor
                    #print ModuleName, "raw accel = ", raw 
                    accel = {}
                    accel["x"] = self.s8tofloat(raw[1])/63
                    accel["y"] = self.s8tofloat(raw[2])/63
                    accel["z"] = self.s8tofloat(raw[3])/63
                    self.sendAccel(accel)
                elif type[3].startswith("0x005f"): 
                    # Button press decriptor
                    #print ModuleName, "button press = ", raw[1]
                    buttons = {"leftButton": (int(raw[1]) & 2) >> 1,
                               "rightButton": int(raw[1]) & 1}
                    self.sendButtons(buttons)
                elif type[3].startswith("0x0025"):
                    # Temperature descri[tor
                    objT, ambT = self.calcTemperature(raw)
                    self.sendTemp(ambT)
                    self.sendIrTemp(objT)
                elif type[3].startswith("0x0038"):
                    relHumidity = self.calcHumidity(raw)
                    self.sendHumidity(relHumidity)
                else:
                    pass
        try:
            self.gatt.kill(9)
            print ModuleName, self.id, " - ", self.friendlyName, \
                " gatt process killed"
        except:
            sys.stderr.write(ModuleName + "Error: could not kill pexpect for" \
                + self.id + " - " + self.friendlyName + "\n")

    def sendAccel(self, accel):
        msg = {"id": self.id,
               "content": "acceleration",
               "data": accel,
               "timeStamp": time.time()}
        for a in self.accelApps:
            self.cbSendMsg(msg, a)

    def sendHumidity(self, relHumidity):
        msg = {"id": self.id,
               "content": "relHumidity",
               "timeStamp": time.time(),
               "data": relHumidity}
        for a in self.humidApps:
            self.cbSendMsg(msg, a)

    def sendTemp(self, ambT):
        msg = {"id": self.id,
               "timeStamp": time.time(),
               "content": "temperature",
               "data": ambT}
        for a in self.tempApps:
            self.cbSendMsg(msg, a)

    def sendIrTemp(self, objT):
        msg = {"id": self.id,
               "timeStamp": time.time(),
               "content": "ir_temperature",
               "data": objT}
        for a in self.irTempApps:
            self.cbSendMsg(msg, a)

    def sendButtons(self, buttons):
        msg = {"id": self.id,
               "timeStamp": time.time(),
               "content": "buttons",
               "data": buttons}
        for a in self.buttonApps:
            self.cbSendMsg(msg, a)

    def processReq(self, req):
        """
        Processes requests from apps.
        Called in a thread and so it is OK if it blocks.
        Called separately for every app that can make requests.
        """
        #print ModuleName, "processReq, req = ", req
        tagStatus = "ok"
        if req["req"] == "init":
            resp = {"name": self.name,
                    "id": self.id,
                    "status": tagStatus,
                    "services": [{"parameter": "temperature",
                                  "frequency": "1.0",
                                  "purpose": "room"},
                                 {"parameter": "ir_temperature",
                                  "frequency": "1.0",
                                  "purpose": "ir temperature"},
                                 {"parameter": "acceleration",
                                  "frequency": "3.0",
                                  "purpose": "access door"},
                                 {"parameter": "rel_humidity",
                                  "frequency": "1.0",
                                  "purpose": "room"},
                                 {"parameter": "buttons",
                                  "frequency": "0",
                                  "purpose": "user_defined"}],
                    "content": "services"}
            self.cbSendMsg(resp, req["id"])
        elif req["req"] == "services":
            # Apps may turn on or off services from time to time
            # So it is necessary to be able to remove as well as append
            # Can't just destory the lists as they may be being used elsewhere
            if req["id"] not in self.tempApps:
                if "temperature" in req["services"]:
                    self.tempApps.append(req["id"])  
            else:
                if "temperature" not in req["services"]:
                    self.tempApps.remove(req["id"])  

            if req["id"] not in self.irTempApps:
                if "ir_temperature" in req["services"]:
                    self.irTempApps.append(req["id"])  
            else:
                if "ir_temperature" not in req["services"]:
                    self.irTempApps.remove(req["id"])  

            if req["id"] not in self.accelApps:
                if "acceleration" in req["services"]:
                    self.irTempApps.append(req["id"])  
            else:
                if "acceleration" not in req["services"]:
                    self.accelApps.remove(req["id"])  

            if req["id"] not in self.humidApps:
                if "rel_humidity" in req["services"]:
                    self.humidApps.append(req["id"])  
            else:
                if "rel_humidity" not in req["services"]:
                    self.humidApps.remove(req["id"])  

            if req["id"] not in self.buttonApps:
                if "buttons" in req["services"]:
                    self.buttonApps.append(req["id"])  
            else:
                if "buttons" not in req["services"]:
                    self.buttonApps.remove(req["id"])  
        else:
            pass

    def configure(self, config):
        """Config is based on what apps are to be connected.
            May be called again if there is a new configuration, which
            could be because a new app has been added.
        """
        if not self.configured:
            self.startApp()
            self.configured = True

if __name__ == '__main__':
    adaptor = Adaptor(sys.argv)
