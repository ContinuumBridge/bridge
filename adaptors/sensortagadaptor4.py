#!/usr/bin/env python

ModuleName = "SensorTag           "

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
            self.tick += 1
            if self.tick == 56:
                # Enable temperature sensor every 30 seconds & take reading
                #print ModuleName, "Enabled temperature"
                self.gatt.sendline('char-write-cmd 0x29 01')
                self.gatt.expect('\[LE\]>')
                #self.gatt.sendline('char-write-cmd 0x26 0100')
            elif self.tick == 60:
                # Allow about a second before reading temperature
                self.tick = 0
                self.gatt.sendline('char-read-hnd 0x25')
                self.gatt.expect('descriptor: .*')
                raw = self.gatt.after.split()
                #print ModuleName, "raw temp = ", raw 
                self.gatt.sendline('char-write-cmd 0x29 00')
                self.gatt.expect('\[LE\]>')
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
                self.temp["ambT"] = ambT
                self.temp["objT"] = objT
                self.temp["timeStamp"] = time.time()
                #print ModuleName, "objT = ", objT, " ambT = ", ambT

            index = self.gatt.expect(['value:.*', pexpect.TIMEOUT], timeout=10)
            if index == 1:
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
                if type[3].startswith("0x002d"): 
                    # Accelerometer descriptor
                    raw = self.gatt.after.split()
                    #print ModuleName, "raw accel = ", raw 
                    self.accel["x"] = self.signExtend(int(raw[1], 16))
                    self.accel["y"] = self.signExtend(int(raw[2], 16))
                    self.accel["z"] = self.signExtend(int(raw[3], 16))
                    self.accel["timeStamp"] = time.time()
                    for a in self.accelReady:
                        self.accelReady[a] = True
                else:
                    pass
        try:
            self.gatt.kill(9)
            print ModuleName, self.id, " - ", self.friendlyName, \
                " gatt process killed"
        except:
            sys.stderr.write(ModuleName + "Error: could not kill pexpect for" \
                + self.id + " - " + self.friendlyName + "\n")

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
        #d1 = defer.Deferred()
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
        #d1.callback(resp)
        #print ModuleName, "processReq resp = ", resp
        #return d1
        return resp

    def configure(self, config):
        """Config is based on what apps are to be connected."""
        for app in config["apps"]:
            self.accelReady[app["id"]] = False
        self.startApp()

if __name__ == '__main__':
    adaptor = Adaptor(sys.argv)
