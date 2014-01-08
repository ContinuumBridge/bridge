#!/usr/bin/env python
# manager9.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
sim = False

import json
import sys
import time
from twisted.internet import threads
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor, defer
from twisted.protocols.basic import LineReceiver
from pprint import pprint
 
class BridgeControlProtocol(LineReceiver):
 
    def __init__(self):
        self.watchTime = time.time()
        self.checkWatchDog = True
        self.watchTick = 0
        #w = threads.deferToThread(self.watchDog)
        self.stopProg = False
        self.devs = []
        self.appDevs = []
        self.apps = []
        self.config = {}

    def connectionMade(self):
        print "Connection made from Bridge"

    def connectionLost(self, reason):
        print "Bridge closed connection"

    def checkCmdThread(self):
        cmd = raw_input("Command > ")
        #print "Command was: ", cmd
        processed = False
        while not processed:
            if cmd == "exit":
                self.stopProg = True
                break
            elif cmd == "":
                cmd = raw_input("Command > ")
            elif cmd == "discover":
                msg  = {"msg": "cmd",
                        "data": "discover"}
                self.sendLine(json.dumps(msg))
                processed = True
            elif cmd == "start" or cmd == "stop" or cmd == "stopapps" \
                         or cmd == "stopall":
                msg  = {"msg": "cmd",
                        "data": cmd}
                self.sendLine(json.dumps(msg))
                cmd = raw_input("Command > ")
            else:
                print "Unrecognised input: ", cmd
                cmd = raw_input("Command > ")
        if self.stopProg:
            reactor.callFromThread(self.doStop)

    def doStop(self):
        try:
            reactor.stop()
            print "Reactor stopped"
        except:
            print "Could not stop reactor"
        sys.exit
            
    def checkCmd(self):
        d = threads.deferToThread(self.checkCmdThread)
        if self.stopProg:
            self.doStop()

    def processDiscovered(self, dat):
        print "processDiscovered: ", dat
        numDevs = len(dat)
        if numDevs != 0:
            if numDevs > 1: 
                print("More than 1 device found. Processing only one")
            currentDev = dat[0]
            #print ("Device - SensorTag: " + msg[str(0)][1])
            print "Device - SensorTag: ", currentDev
            friendly = raw_input("Type friendly name  > ")
            gotPurpose = False
            while not gotPurpose:
                purpose = \
                    raw_input("Type purpose (fridge | door | activity | x  > ")
                if purpose != "fridge" and purpose != "door" \
                    and purpose != "activity" and purpose != "x":
                    print("Unrecognised purpose. Please re-enter.")
                else:
                    gotPurpose = True
            self.buildBridgeData(friendly, purpose, currentDev) 
        else:
            print("No devices found. Try again.")
            self.checkCmd()

    def buildBridgeData(self, friendly, purpose, currentDev):
        numDevs = len(self.devs)
        devNum = numDevs + 1
        if sim:
            exe = 'testSensorTagAdaptor.py'
        else:
            exe = 'sensortagadaptor.py'
        dev =  \
              {"adaptor_install": [
                {
                 "name": currentDev["name"],
                 "friendlyName": friendly,
                 "id": "dev" + str(devNum),
                 "btAddr": currentDev["addr"],
                 "adaptor": 
                   {
                    "name": "CB SensorTag Adt",
                    "provider": "ContinuumBridge",
                    "purpose": purpose,
                    "method": currentDev["method"],
                    "version": 2,
                    "url": "www.continuumbridge.com/adt/cbSensorTagAdtV2",
                    "exe": exe,
                    "resource_uri": "/api/V1/device/" + str(devNum)
                    },
                 "device": "/api/v1/device/" + str(devNum),
                 "id": str(devNum),
                 "resource_uri": "/api/v1/adaptor_install/" + str(devNum)
                 }
                ],
               "bridge": "random bridge test text",
               "device": "random device test text",
               "id": str(devNum),
               "mac_addr": currentDev["addr"],
               "resource_url": "/api/V1/device/" + str(devNum)
              }
        self.devs.append(dev)

        appDev = {
                  "device_install": "/api/v1/adaptor_install/" + str(devNum),
                  "resource_uri": "/api/v1/app_device_permission/1/"
                 } 
        self.appDevs.append(appDev)
 
        numApps = len(self.apps)
        if numApps == 0:
            appNum = numApps + 1
            app = {"app":{"id": str(appNum),
                          "name": "living",
                          "provider": "ContinuumBridge",
                          "version": 2,
                          "url": "www.continuumbridge.com/apps/cbLivingV2",
                          "exe": "uwe_app.py",
                          "resource_uri": "/api/v1/app/" + str(appNum)
                         },
                   "bridge": "",
                   "device_permissions": self.appDevs,
                   "id": str(appNum),
                   "resource_uri": "/api/v1/app_install/" + str(appNum)
                  }
            self.apps.append(app)
#            appNum = appNum + 1
#            app = {"app":{"id": str(appNum),
#                          "name": "Temp Monitor",
#                          "provider": "ContinuumBridge",
#                          "version": 2,
#                          "url": "www.continuumbridge.com/apps/cbtempmonitor",
#                          "exe": "tempmonitor.py",
#                          #"exe": "testLiving.py",
#                          "resource_uri": "/api/v1/app/" + str(appNum)
#                         },
#                   "bridge": "",
#                   "devices": self.appDevs,
#                   "id": str(appNum),
#                   "resource_uri": "/api/v1/app_install/" + str(appNum)
#                  }
#            self.apps.append(app)
#    
        self.config = {"msg": "resp",
                       "uri": "/api/vi/current_bridge/bridge",
                       "data": {"id": 42,
                                "friendlyName": "Friendly Bridge",
                                "bridgeManager": "cbmanager.py",
                                "backupManager": "manager7.py",
                                "email": "28b45a59a875478ebcbdf327c18dbfb1@continuumbridge.com",
                                "resource_uri": "/api/v1/current_bridge/42/",
                                "devices": self.devs,
                                "apps": self.apps
                               }
                      }
        self.sendLine(json.dumps(self.config))
    
    def lineReceived(self, rawMsg):
        print "Message received: ", rawMsg
        self.watchTime = time.time()
        msg = json.loads(rawMsg)
        if msg["msg"] == "req":
            if msg["req"] == "get":
                print "Sync requested"
                self.sendLine(json.dumps(self.config))
            elif msg["req"] == "discovered":
                print "Discovered devices:"
                pprint(msg)
                self.processDiscovered(msg["data"])
                self.checkCmd()
            elif msg["req"] == "reqSync":
                print "Sync requested"
                self.sendLine(json.dumps(self.config))
        elif msg["msg"] == "status":
            if msg["data"] == "ready":
                print "Bridge ready"
                self.checkCmd()
            elif msg["data"] == "reqSync":
                print "Sync requested"
                self.sendLine(json.dumps(self.config))
            elif msg["data"] != "ok":
                print "Unknown message received from bridge" 
        else:
            print "Unknown message received from bridge" 
      
if __name__ == '__main__':
 
    if len(sys.argv) < 2:
        print "Usage: manager <bridge ip address>:<bridge socket>"
        exit(1)
    bridgeSoc = sys.argv[1]

    bridgeSocFactory=Factory()
    bridgeSocFactory.protocol = BridgeControlProtocol

    try:
        reactor.listenTCP(int(bridgeSoc), bridgeSocFactory)
        print "Opened Bridge socket ", bridgeSoc
    except:
        print "Failed to open Bridge socket ", bridgeSoc

    reactor.run()
