#!/usr/bin/env python

ModuleName = "Accel Adaptor       "

import pexpect
import sys
import time
import os
import atexit
import pdb
import json
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor

class ManageAccelerometer:
    def __init__(self):
        self.connected = False

    def initSensorTag(self, device, addr):
        try:
            cmd = 'gatttool -i ' + device + ' -b ' + addr + ' --interactive'
            gatt = pexpect.spawn(cmd)
        except:
            print ModuleName, "pexpect failed to spawn"
            self.connected = False
            return
        gatt.expect('\[LE\]>')
        gatt.sendline('connect')
        gatt.expect('\[LE\]>', timeout=5)
        gatt.expect('successful', timeout=5)
        # Enable accelerometer
        gatt.sendline('char-write-cmd 0x31 01')
        gatt.expect('\[LE\]>')
        gatt.sendline('char-write-cmd 0x2e 0100')
        gatt.expect('\[LE\]>')
        gatt.sendline('char-write-cmd 0x34 0a')
        gatt.expect('\[LE\]>')
        self.connected = True
        return gatt

    def isConnected(self):
        return self.connected

    def signExtend(self, a):
        if a > 127:
            a = a - 256
        return a

    def getAccel(self, gatt):
        # Need first gatt.expect as there is always a command prompt 
        gatt.expect('\[LE\]>')
        gatt.expect('value: .*')
        raw = gatt.after.split()
        accel = {}
        accel["x"] = self.signExtend(int(raw[1], 16))
        accel["y"] = self.signExtend(int(raw[2], 16))
        accel["z"] = self.signExtend(int(raw[3], 16))
        return accel

    def processReq(self, req):
        response = {}
        if req["cmd"] == "init":
            response = {"id": "accel",
                        "status": "ok",
                        "content": "none"}
        elif req["cmd"] == "send-accel":
            response = {"id": "accel",
                        "content": "data", 
                        "data": self.getAccel(gatttool)}
        return response

class Accel(Protocol):
    def dataReceived(self, data):
        response = m.processReq(json.loads(data))
        #line = json.dumps(str(m.getAccel(gatttool))) + "\r\n" 
        self.transport.write(json.dumps(response) + "\r\n")
    def connectionMade(self):
        print ModuleName, "Connection made to ", self.transport.getPeer()
    def connectionLost(self, reason):
        print ModuleName, "Disconnected"

print ModuleName, "Hello from the twisted accelerometer adaptor"

if len(sys.argv) < 4:
    print ModuleName, "Wrong number of arguments"
    exit(1)

device = sys.argv[1]
addr = sys.argv[2]
mgrSocket = sys.argv[3]
adaptorSocket = sys.argv[4]

#print ModuleName, "Args: ", device, addr, mgrSocket, adaptorSocket
#os.system("sudo hciconfig " + device + " reset")

m = ManageAccelerometer()
gatttool = m.initSensorTag(device, addr)

if m.isConnected():
    print ModuleName, "Successfully connected to SensorTag"
else:
    print ModuleName, "Could not connect to Sensortag"

f=Factory()
f.protocol = Accel
reactor.listenUNIX(adaptorSocket, f, backlog=4)
reactor.run()

