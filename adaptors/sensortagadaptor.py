#!/usr/bin/env python
# sensortagadaptor5.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "SensorTag           "

import pexpect
import sys
import time
import os
from cbcommslib import CbAdaptor
#from threading import Thread
from twisted.internet import threads
from twisted.internet import reactor

class SimValues():
    """ Provides values in sim mode (without a real SensorTag connected). """
    def __init__(self):
        self.tick = 0

    def getSimValues(self):
        # Acceleration every 330 ms, everything else every 990 ms
        if self.tick == 0:
            # Acceleration
            raw =  ['handle', '=', '0x002d', 'value:', 'ff', 'c2', '01', 'xxx[LE]>']
        elif self.tick == 1:
            time.sleep(0.20)
            # Temperature
            raw =  ['handle', '=', '0x0025', 'value:', 'fc', 'ff', 'ec', '09', 'xxx[LE]>']
        elif self.tick == 2:
            time.sleep(0.13)
            # Acceleration
            raw = ['handle', '=', '0x002d', 'value:', 'ff', 'c2', '01', 'xxx[LE]>']
        elif self.tick == 3:
            time.sleep(0.20)
            # Rel humidity
            raw = ['handle', '=', '0x0038', 'value:', 'c0', '61', 'ae', '7e', 'xxx[LE>']
        elif self.tick == 4:
            time.sleep(0.13)
            # Acceleration
            raw = ['handle', '=', '0x002d', 'value:', 'ff', 'c2', '01', 'xxx[LE]>']
        elif self.tick == 5:
            time.sleep(0.20)
            # Gyro
            raw = ['handle', '=', '0x0057', 'value:', '28', '00', 'cc', 'ff', 'c3', 'ff', 'xxx[LE]>']
        elif self.tick == 6:
            time.sleep(0.14)
            # Acceleration
            raw = ['handle', '=', '0x002d', 'value:', 'ff', 'c2', '01', 'xxx[LE]>']
        self.tick = (self.tick + 1)%7
        return raw

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        #CbAdaptor methods processReq & cbAdtConfig MUST be subclassed
        CbAdaptor.processReq = self.processReq
        CbAdaptor.cbAdtConfigure = self.configure
        self.connected = False  # Indicates we are connected to SensorTag
        self.status = "ok"
        self.tempApps = []
        self.irTempApps = []
        self.accelApps = []
        self.humidApps = []
        self.gyroApps = []
        self.buttonApps = []
        #CbAdaprot.__init__ MUST be called
        CbAdaptor.__init__(self, argv)

    def initSensorTag(self):
        print ModuleName, "initSensorTag", self.id, " - ", self.friendly_name
        # Ensure that the Bluetooth interface is up
        try:
            os.system("sudo hciconfig hci0 up")
        except:
            print ModuleName, "Unable to bring up hci0 interface"
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
                " - ", self.friendly_name
            self.gatt.kill(9)
            return "timeout"
        else:
            print ModuleName, self.id, " - ", self.friendly_name, " connected"
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
 
            # Enable gyro with notification
            # Write 0 to turn off gyroscope, 1 to enable X axis only, 2 to
            # enable Y axis only, 3 = X and Y, 4 = Z only, 5 = X and Z, 6 =
            # Y and Z, 7 = X, Y and Z
            self.gatt.sendline('char-write-cmd 0x5B 07')
            self.gatt.expect('\[LE\]>')
            self.gatt.sendline('char-write-cmd 0x58 0100')
            self.gatt.expect('\[LE\]>')

            # Enable button-press notification
            self.gatt.sendline('char-write-cmd 0x60 0100')
            self.gatt.expect('\[LE\]>')
            # We're connected!
            self.connected = True
            print ModuleName, self.id, " - ", self.friendly_name, " configured"
            return "ok"

    def startApp(self):
        """
        Continually attempts to connect to the device.
        Gating with doStop needed because adaptor may be stopped before
        the device is ever connected.
        """
        if self.connected == True:
            tagStatus = "Already connected" # Indicates app restarting
        elif self.sim != 0:
            # In simulation mode (no real devices) just pretend to connect
            self.connected = True
        while self.connected == False and not self.doStop and self.sim == 0:
            tagStatus = self.initSensorTag()    
            if tagStatus != "ok":
                print ModuleName
                print ModuleName, "ERROR. ", self.id, " - ", \
                    self.friendly_name, " failed to initialise"
                print ModuleName, "Please press side button"
                print ModuleName, \
                      "If problem persists SensorTag may be out of range"
        if not self.doStop:
            # Start a thread that continually gets accel and temp values
            reactor.callInThread(self.getValues)
            print ModuleName, self.id, " - ", self.friendly_name, \
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
        objT = self.s16tofloat(raw[1] + \
                            raw[0]) * 0.00000015625
        ambT = self.s16tofloat(raw[3] + raw[2]) / 128.0
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
        t1 = self.s16tofloat(raw[1] + raw[0])
        temp = -46.85 + 175.72/65536 * t1
        rawH = int((raw[3] + raw[2]), 16) & 0xFFFC # Clear bits [1:0] - status
        # Calculate relative humidity [%RH] 
        v = -6.0 + 125.0/65536 * float(rawH) # RH= -6 + 125 * SRH/2^16
        return v

    def calcGyro(self, raw):
        # Xalculate rotation, unit deg/s, range -250, +250
        r = self.s16tofloat(raw[1] + raw[0])
        v = (r * 1.0) / (65536/500)
        return v

    def getValues(self):
        """Continually updates accel and temp values.

        Run in a thread. When new accel values are received, the thread
        sets the accelReady flag for each attached app to True.  
        """
        while not self.doStop:
            if self.sim == 0:
                index = self.gatt.expect(['handle.*', pexpect.TIMEOUT], timeout=10)
            else:
                index = 0
            if index == 1:
                # A timeout error. Attempt to restart the SensorTag
                status = ""
                while status != "ok" and not self.doStop:
                    print ModuleName, self.id, " - ", self.friendly_name, \
                        " gatt timeout"
                    self.gatt.kill(9)
                    time.sleep(1)
                    status = self.initSensorTag()   
                    print ModuleName, self.id, " - ", self.friendly_name, \
                        " re-init status = ", status
            else:
                if self.sim == 0:
                    raw = self.gatt.after.split()
                else:
                    raw = self.simValues.getSimValues()
                #print ModuleName, "raw from SensorTag = ", raw
                handles = True
                startI = 2
                while handles:
                    type = raw[startI]
                    if type.startswith("0x002d"): 
                        # Accelerometer descriptor
                        #print ModuleName, "raw accel = ", raw 
                        accel = {}
                        accel["x"] = self.s8tofloat(raw[startI+2])/63
                        accel["y"] = self.s8tofloat(raw[startI+3])/63
                        accel["z"] = self.s8tofloat(raw[startI+4])/63
                        self.sendAccel(accel)
                    elif type.startswith("0x005f"): 
                        # Button press decriptor
                        #print ModuleName, "button press = ", raw[1]
                        buttons = {"leftButton": (int(raw[startI+2]) & 2) >> 1,
                                   "rightButton": int(raw[startI+2]) & 1}
                        self.sendButtons(buttons)
                    elif type.startswith("0x0025"):
                        # Temperature descriptor
                        objT, ambT = self.calcTemperature(raw[startI+2:startI+6])
                        self.sendTemp(ambT)
                        self.sendIrTemp(objT)
                    elif type.startswith("0x0038"):
                        relHumidity = self.calcHumidity(raw[startI+2:startI+6])
                        self.sendHumidity(relHumidity)
                    elif type.startswith("0x0057"):
                        gyro = {}
                        gyro["x"] = self.calcGyro(raw[startI+2:startI+4])
                        gyro["y"] = self.calcGyro(raw[startI+4:startI+6])
                        gyro["z"] = self.calcGyro(raw[startI+6:startI+8])
                        #print ModuleName, "gyro = ", gyro
                        self.sendGyro(gyro)
                    else:
                       pass
                    # There may be more than one handle in raw. Remove the
                    # first occurence & if there is another process it
                    raw.remove("handle")
                    if "handle" in raw:
                        handle = raw.index("handle")
                        #print ModuleName, "handle = ", handle
                        startI = handle + 2
                    else:
                        handles = False
        try:
            if self.sim == 0:
                self.gatt.kill(9)
                print ModuleName, self.id, " - ", self.friendly_name, \
                    " gatt process killed"
        except:
            sys.stderr.write(ModuleName + "Error: could not kill pexpect for" \
                + self.id + " - " + self.friendly_name + "\n")

    def sendAccel(self, accel):
        msg = {"id": self.id,
               "content": "acceleration",
               "data": accel,
               "timeStamp": time.time()}
        for a in self.accelApps:
            reactor.callFromThread(self.cbSendMsg, msg, a)

    def sendHumidity(self, relHumidity):
        msg = {"id": self.id,
               "content": "relHumidity",
               "timeStamp": time.time(),
               "data": relHumidity}
        for a in self.humidApps:
            reactor.callFromThread(self.cbSendMsg, msg, a)

    def sendTemp(self, ambT):
        msg = {"id": self.id,
               "timeStamp": time.time(),
               "content": "temperature",
               "data": ambT}
        for a in self.tempApps:
            reactor.callFromThread(self.cbSendMsg, msg, a)

    def sendIrTemp(self, objT):
        msg = {"id": self.id,
               "timeStamp": time.time(),
               "content": "ir_temperature",
               "data": objT}
        for a in self.irTempApps:
            reactor.callFromThread(self.cbSendMsg, msg, a)

    def sendButtons(self, buttons):
        msg = {"id": self.id,
               "timeStamp": time.time(),
               "content": "buttons",
               "data": buttons}
        for a in self.buttonApps:
            reactor.callFromThread(self.cbSendMsg, msg, a)

    def sendGyro(self, gyro):
        msg = {"id": self.id,
               "content": "gyro",
               "data": gyro,
               "timeStamp": time.time()}
        for a in self.gyroApps:
            reactor.callFromThread(self.cbSendMsg, msg, a)

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
                                 {"parameter": "gyro",
                                  "frequency": "1.0",
                                  "range": "-250:+250 degrees",
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
                    self.accelApps.append(req["id"])  
            else:
                if "acceleration" not in req["services"]:
                    self.accelApps.remove(req["id"])  

            if req["id"] not in self.humidApps:
                if "rel_humidity" in req["services"]:
                    self.humidApps.append(req["id"])  
            else:
                if "rel_humidity" not in req["services"]:
                    self.humidApps.remove(req["id"])  

            if req["id"] not in self.gyroApps:
                if "gyro" in req["services"]:
                    self.gyroApps.append(req["id"])  
            else:
                if "gyro" not in req["services"]:
                    self.gyroApps.remove(req["id"])  

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
            if self.sim != 0:
                self.simValues = SimValues()
            self.startApp()
            self.configured = True

if __name__ == '__main__':
    adaptor = Adaptor(sys.argv)
