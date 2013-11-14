#!/usr/bin/env python

ModuleName = "SensorTag           "

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
    def __init__(self):
        self.connected = False
        self.status = "ok"
        self.fetchValues = True #Set to False to stop fetch thread
        self.accel = {} #To hold latest accel values
        self.accelReady = False #No accel values at start of time
        self.startTime = time.time()
        self.accelCount = 0
        self.tick = 0
        self.temp = {}  #To hold temperature values
        self.temp["ambT"] = 0
        self.temp["objT"] = 0
        self.temp["timeStamp"] = time.time()
        self.doingTemp = False

    def initSensorTag(self):
        print ModuleName, "initSensorTag"
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
            self.gatt.kill(9)
            return "timeout"
        else:
            print ModuleName, "Connected"
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
        """ Updates accel and temp values
        """
        while self.fetchValues:
            self.tick += 1
            if self.tick == 60:
                # Enable temperature sensor every 30 seconds & take reading
                self.gatt.sendline('char-write-cmd 0x29 01')
                self.gatt.sendline('char-write-cmd 0x26 0100')
                self.tick = 0
                self.doingTemp = True
            index = self.gatt.expect(['value:.*', pexpect.TIMEOUT], timeout=5)
            if index == 1:
                status = ""
                #print ModuleName, "type = ", type
                while status != "ok" and self.fetchValues:
                    print ModuleName, "Gatt timeout"
                    self.gatt.kill(9)
                    time.sleep(1)
                    status = self.initSensorTag()   
                    print ModuleName, "Re-init status = ", status
            else:
                type = self.gatt.before.split()
                if type[3].startswith("0x002d"): 
                    # Accelerometer descriptor
                    raw = self.gatt.after.split()
                    self.accel["x"] = self.signExtend(int(raw[1], 16))
                    self.accel["y"] = self.signExtend(int(raw[2], 16))
                    self.accel["z"] = self.signExtend(int(raw[3], 16))
                    self.accel["timeStamp"] = time.time()
                    self.accelReady = True
                elif type[3].startswith("0x0025") and self.doingTemp:
                    # Temperature descriptor
                    raw = self.gatt.after.split()
                    # Disable temperature notification & sensor
                    self.gatt.sendline('char-write-cmd 0x26 0100')
                    self.gatt.sendline('char-write-cmd 0x29 00')
                    self.doingTemp = False # So that we only do this once
    
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
                    #print ModuleName, "temp = ", self.temp
                else:
                   pass
                   #print ModuleName, "Unknown gatt: ", type[3], "." \
                         #" doingTemp = ", self.doingTemp
     
    def reqAccel(self):
        while self.accelReady == False:
            time.sleep(0.05) 
        accel = self.accel
        # Check how often we're actually getting accel values
        #self.accelCount = self.accelCount + 1
        #if accel["timeStamp"] - self.startTime > 10:
            #print ModuleName, id, " readings in 10s = ", self.accelCount
            #self.accelCount = 0
            #self.startTime = accel["timeStamp"]        
        self.accelReady = False
        return accel 

    def reqTemp(self):
        return self.temp
    
    def processReq(self, req):
        """ Processes requests from apps """
        #print ModuleName, "processReq", req
        d1 = defer.Deferred()
        if req["req"] == "init" or req["req"] == "char":
            if self.connected == True:
                tagStatus = "Already connected" # Indicates app restarting
            while self.connected == False:
                tagStatus = self.initSensorTag()    
                if tagStatus != "ok":
                    print ModuleName
                    print ModuleName, "ERROR. SensorTag ", id, \
                        " failed to initialise"
                    print ModuleName, "Please press side button"
                    print ModuleName, \
                          "If problem persists SensorTag may be out of range"
            # Start a thread that continually gets accel and temp values
            d2 = threads.deferToThread(self.getValues)
            print ModuleName, id, " successfully initialised"
            resp = {"name": self.name,
                    "id": id,
                    "status": tagStatus,
                    "capabilities": {"accelerometer": "0.1",
                                     "temperature": "5"},
                    "content": "none"}
        elif req["req"] == "req-data":
            resp = {"name": self.name,
                    "id": id,
                    "status": "ok",
                    "content": "data", 
                    "accel": self.reqAccel(),
                    "temp": self.reqTemp()}
        else:
            resp = {"name": self.name,
                    "id": id,
                    "status": "bad-req",
                    "content": "none"}
        d1.callback(resp)
        return d1

    def configure(self, config):
        """ Config is based on what sensors are available """
        print ModuleName, "configure: ", config
        self.name = config["name"]
        self.device = config["btAdpt"]
        self.addr = config["btAddr"]
        self.cbFactory = []
        self.appInstances = []
        for app in config["apps"]:
            name = app["name"]
            id = app["id"]
            adtSoc = app["adtSoc"]
            self.appInstances.append(id)
            self.cbFactory.append(Factory())
            self.cbFactory[-1].protocol = cbAdaptorProtocol
            reactor.listenUNIX(adtSoc, self.cbFactory[-1])

    def cbManagerMsg(self, cmd):
        #print ModuleName, id, " received from manager: ", cmd
        if cmd["cmd"] == "stop":
            print ModuleName, id, " stopping"
            self.fetchValues = False
            msg = {"id": id,
                   "status": "stopping"}
            time.sleep(10)
            reactor.stop()
            sys.exit
        elif cmd["cmd"] == "config":
            self.configure(cmd["config"])
            msg = {"id": id,
                   "status": "ok"}
        elif cmd["cmd"] != "ok":
            msg = {"id": id,
                   "status": "unknown"}
        else:
            msg = {"id": id,
                   "status": "none"}
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
        msg = {"id": id,
               "class": "adt",
               "status": "req-config"}
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
    
    if len(sys.argv) < 3:
        print ModuleName, "Wrong number of arguments"
        exit(1)
    
    managerSocket = sys.argv[1]
    id = sys.argv[2]
    
    p = ManageTag()
   
    # Socket for connecting to the bridge manager
    managerFactory = cbClientFactory()
    managerFactory.protocol = cbManagerClient
    reactor.connectUNIX(managerSocket, managerFactory, timeout=10)
    
    reactor.run()
    
