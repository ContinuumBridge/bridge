#!/usr/bin/env python

ModuleName = "SensorTag           "
id = "sensortagadaptor"

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
from twisted.internet import threads
from twisted.internet import defer

class ManageTag:
    status = "ok"
    def __init__(self, device, addr):
        self.device = device
        self.addr = addr
        self.connected = False
        self.status = "ok"
        self.accel = {} #To hold latest accel values
        self.accelReady = False #No accel values at start of time
        self.fetchAccel = False

    def initSensorTag(self):
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
            print ModuleName, "Connection to device timed out"
            self.gatt.kill(0)
            return "timeout"
        else:
            # Enable accelerometer
            self.gatt.sendline('char-write-cmd 0x31 01')
            self.gatt.expect('\[LE\]>')
            self.gatt.sendline('char-write-cmd 0x2e 0100')
            self.gatt.expect('\[LE\]>')
            # Period = 0x34 value x 10 ms
            self.gatt.sendline('char-write-cmd 0x34 0a')
            self.gatt.expect('\[LE\]>')
            self.connected = True
            return "ok"

    def signExtend(self, a):
        if a > 127:
            a = a - 256
        return a

    def getAccel(self):
        """ Updates accel values
        """
        # Need first gatt.expect as there is always a command prompt 
        #print ModuleName, "In getAccel"
        self.gatt.expect('\[LE\]>')
        self.gatt.expect('value: .*')
        raw = self.gatt.after.split()
        updatingAccel = True #To prevent access during update
        accel = {}
        accel["x"] = self.signExtend(int(raw[1], 16))
        accel["y"] = self.signExtend(int(raw[2], 16))
        accel["z"] = self.signExtend(int(raw[3], 16))
        accel["time"] = time.time()
        self.updatingAccel = False
        return accel

    def reqAccel(self):
        accel = self.getAccel()
        return accel 
    
    def processReq(self, req):
        """ Processes requests from apps """
        #print ModuleName, "processReq", req
        d1 = defer.Deferred()
        if req["req"] == "init" or req["req"] == "char":
            tagStatus = self.initSensorTag()    
            resp = {"name": "sensortag",
                    "instance": "sensortag1",
                    "status": tagStatus,
                    "capabilities": {"accelerometer": "0.1"},
                    "content": "none"}
            print ModuleName, "SensorTag initialised"
        elif req["req"] == "req-accel":
            resp = {"name": "sensortag",
                    "instance": "sensortag1",
                    "status": "ok",
                    "content": "accel", 
                    "data": self.reqAccel()}
        elif req["req"] == "req-temp":
            resp = {"name": "sensortag",
                    "instance": "sensortag1",
                    "status": "ok",
                    "content": "temp", 
                    "data": "wip"}
        else:
            resp = {"name": "sensortag",
                    "instance": "sensortag1",
                    "status": "bad-req",
                    "content": "none"}
        d1.callback(resp)
        return d1

    def cbManagerMsg(self, cmd):
        #print ModuleName, "Received from manager: ", cmd
        if cmd["cmd"] == "stop":
            print ModuleName, "Stopping"
            self.fetchAccel = False
            msg = {"id": id,
                   "status": "stopping"}
            time.sleep(1)
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

class cbAdaptorProtocol(LineReceiver):
    def lineReceived(self, data):
        self.d1 = p.processReq(json.loads(data))
        self.d1.addCallback(self.sendResp)

    def sendResp(self, resp):
        self.sendLine(json.dumps(resp))

class cbManagerClient(LineReceiver):
    def connectionMade(self):
        msg = {"name": id,
               "status": "hello"}
        self.sendLine(json.dumps(msg))
        reactor.callLater(5, self.monitorProcess)

    def lineReceived(self, line):
        managerMsg = json.loads(line)
        msg = p.cbManagerMsg(managerMsg)
        if msg["status"] != "none":
            self.sendLine(json.dumps(msg))

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
    
    p = ManageTag(device, addr)
   
    # Socket for connecting to the bridge manager
    managerFactory = cbClientFactory()
    managerFactory.protocol = cbManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    
    # Socket for connecting to the app (in future there will be more)
    f=Factory()
    f.protocol = cbAdaptorProtocol
    reactor.listenUNIX(adaptorSocket, f, backlog=4)
    reactor.run()
    
