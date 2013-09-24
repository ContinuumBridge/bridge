#!/usr/bin/env python

ModuleName = "Accel Adaptor       "
id = "acceladaptor2"

import pexpect
import sys
import time
import os
import atexit
import pdb
import json
from twisted.internet.protocol import Protocol, Factory
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import reactor

class ManageAccelerometer:
    status = "ok"
    def __init__(self):
        self.connected = False
        self.status = "ok"

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

    def processManagerMsg(self, cmd):
        #print ModuleName, "Received from manager: ", cmd
        if cmd["cmd"] == "stop":
            print ModuleName, "Stopping"
            msg = {"id": id,
                   "status": "stopping"}
            reactor.stop()
            sys.exit
        elif cmd["cmd"] != "ok":
            msg = {"id": id,
                   "status": "unknown"}
        else:
            msg = {"status": "none"}
        return msg

    def reportStatus(self):
        return self.status

    def setStatus(self, newStatus):
        self.status = newStatus

class Accel(Protocol):
    def dataReceived(self, data):
        response = p.processReq(json.loads(data))
        #line = json.dumps(str(p.getAccel(gatttool))) + "\r\n" 
        self.transport.write(json.dumps(response) + "\r\n")

    def connectionMade(self):
        print ModuleName, "Connection made to app ", self.transport.getPeer()

    def connectionLost(self, reason):
        print ModuleName, "Disconnected from app"

class ManagerClient(LineReceiver):
    def connectionMade(self):
        msg = {"id": id,
               "status": "hello"}
        self.sendLine(json.dumps(msg))
        reactor.callLater(5, self.monitorProcess)

    def lineReceived(self, line):
        managerMsg = json.loads(line)
        msg = p.processManagerMsg(managerMsg)
        if msg["status"] != "none":
            self.sendLine(json.dumps(msg))

    def monitorProcess(self):
        msg = {"id": id,
               "status": p.status}
        self.sendLine(json.dumps(msg))
        p.status = "ok"
        reactor.callLater(2, self.monitorProcess)

    def monitorProcess(self):
        msg = {"id": id,
               "status": p.reportStatus()}
        self.sendLine(json.dumps(msg))
        p.setStatus("ok")
        reactor.callLater(2, self.monitorProcess)

class cbClientFactory(ReconnectingClientFactory):

    def clientConnectionFailed(self, connector, reason):
        print ModuleName, "Failed to connect:", \
              reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        print ModuleName, "Connection lost:", \
              reason.getErrorMessage()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

if __name__ == '__main__':
    print ModuleName, "Hello"
    
    if len(sys.argv) < 4:
        print ModuleName, "Wrong number of arguments"
        exit(1)
    
    device = sys.argv[1]
    addr = sys.argv[2]
    managerSocket = sys.argv[3]
    adaptorSocket = sys.argv[4]
    
    p = ManageAccelerometer()
    gatttool = p.initSensorTag(device, addr)
    
    if p.isConnected():
        print ModuleName, "Successfully connected to SensorTag"
    else:
        print ModuleName, "Could not connect to Sensortag"
    
    managerFactory = cbClientFactory()
    managerFactory.protocol = ManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    
    f=Factory()
    f.protocol = Accel
    reactor.listenUNIX(adaptorSocket, f, backlog=4)
    reactor.run()
    
