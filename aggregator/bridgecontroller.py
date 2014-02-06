#!/usr/bin/env python
# manager9.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#

import json
import sys
import time
from twisted.internet import threads
from twisted.internet import reactor, defer
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory
from pprint import pprint
 
class BridgeControl:
 
    def __init__(self):
        self.watchTime = time.time()
        self.checkWatchDog = True
        self.watchTick = 0
        self.stopProg = False
        self.devs = []
        self.appDevs = []
        self.apps = []
        self.config = {}
        self.bridgePort = 5000
        self.cbFactory = CbServerFactory(self.processResp)
        reactor.callLater(0.5, self.startListening)
        reactor.callLater(1, self.checkCmd)
        reactor.run()

    def cbSendMsg(self, msg):
        self.cbFactory.sendMsg(msg)

    def startListening(self):
        try:
            self.mgrListen = reactor.listenTCP(self.bridgePort, self.cbFactory, backlog=4)
            print "Lisening on Bridge port > ", self.bridgePort
        except:
            print "Failed to listen on Bridge port > ", self.bridgePort

    def checkCmdThread(self):
        processed = False
        while not processed:
            cmd = raw_input("Command > ")
            if cmd == "exit":
                self.stopProg = True
                processed = True
            elif cmd == "discover":
                msg  = {"msg": "cmd",
                        "body": "discover"}
                print "Sending command to bridge: > ", msg
                reactor.callFromThread(self.cbSendMsg, msg)
                processed = True
            #elif cmd == "start" or cmd == "stop" or cmd == "stopapps" \
                         #or cmd == "stopall":
            elif cmd in ["start", "stop", "stopapps", "stopall"]:
                msg  = {"msg": "cmd",
                        "body": cmd}
                print "Sending command to bridge: > ", msg
                reactor.callFromThread(self.cbSendMsg, msg)
            elif cmd in ["restart", "reboot"]:
                msg  = {"msg": "cmd",
                        "body": cmd}
                print "Sending command to bridge: > ", msg
                reactor.callFromThread(self.cbSendMsg, msg)
                reactor.callFromThread(self.reconnect)
            elif cmd == "update_config" or cmd == "update":
                msg  = {"msg": "cmd",
                        "body": "update_config"}
                print "Sending command to bridge: > ", msg
                reactor.callFromThread(self.cbSendMsg, msg)
            elif cmd == "":
                pass
            else:
                print "Unrecognised input: > ", cmd
        if self.stopProg:
            reactor.callFromThread(self.doStop)

    def doStop(self):
        try:
            reactor.stop()
            print "Reactor stopped"
        except:
            print "Could not stop reactor"
        sys.exit

    def reconnect(self):
        reactor.callLater(10, self.stopListen)

    def stopListen(self):
        self.mgrListen.stopListening()
        reactor.callLater(5, self.startListening)
            
    def checkCmd(self):
        reactor.callInThread(self.checkCmdThread)

    def processDiscovered(self, dat):
        #print "processDiscovered: ", dat
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
            print("No devices found. Please try again.")
        self.checkCmd()

    def buildBridgeData(self, friendly, purpose, currentDev):
        numDevs = len(self.devs)
        devNum = numDevs + 1
        exe = 'sensortagadaptor.py'
        dev =  \
              {"adaptor":
                {
                 "name": currentDev["name"],
                 "id": devNum,
                 "name": "CB SensorTag Adt",
                 "provider": "ContinuumBridge",
                 "purpose": purpose,
                 "protocol": currentDev["protocol"],
                 "version": 2,
                 "url": "www.continuumbridge.com/adt/cbSensorTagAdtV2",
                 "exe": exe,
                 "device": "/api/v1/device/" + str(devNum),
                 "resource_uri": "/api/v1/adaptor/" + str(devNum)
                 },
               "bridge": "random bridge test text",
               "device": "random device test text",
               "id": devNum,
               "friendly_name": friendly,
               "mac_addr": currentDev["mac_addr"],
               "resource_uri": "/api/v1/device_install/" + str(devNum)
              }
        self.devs.append(dev)

        appDev = {
                  "device_install": "/api/v1/device_install/" + str(devNum),
                  "resource_uri": "/api/v1/app_device_permission/1/"
                 } 
        self.appDevs.append(appDev)
 
        numApps = len(self.apps)
        if numApps == 0:
            appNum = numApps + 1
            app = {"app":{"id": appNum,
                          "name": "living",
                          "provider": "ContinuumBridge",
                          "version": 2,
                          "url": "www.continuumbridge.com/apps/cbLivingV2",
                          "exe": "uwe_app.py",
                          "resource_uri": "/api/v1/app/" + str(appNum)
                         },
                   "bridge": "",
                   "device_permissions": self.appDevs,
                   "id": appNum,
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
        self.config = {"msg": "response",
                       "uri": "/api/vi/current_bridge/bridge",
                       "body": {"id": 42,
                                "bridgeManager": "cbmanager.py",
                                "backupManager": "manager7.py",
                                "email": "28b45a59a875478ebcbdf327c18dbfb1@continuumbridge.com",
                                "resource_uri": "/api/v1/current_bridge/42/",
                                "devices": self.devs,
                                "apps": self.apps
                               }
                      }
        #self.cbSendMsg(self.config)
    
    def processResp(self, msg):
        print "Message received: ", msg
        if msg["msg"] == "req":
            if "req" in msg:
                if msg["req"] == "get":
                    if msg["uri"] == "/api/v1/current_bridge/bridge":
                        print "Config requested > "
                        self.cbSendMsg(self.config)
                    else:
                        print "Unrecognised GET > "
            elif "verb" in msg:
                if msg["verb"] == "post":
                    if msg["uri"] == "/api/v1/device_discovery":
                        print "Discovered devices:"
                        pprint(msg)
                        self.processDiscovered(msg["body"])
                    else:
                        print "Unrecognised POST > "
            else:
                print "Unrecognised req from bridge > "
        elif msg["msg"] == "status":
            if msg["body"] == "ready":
                print "Bridge ready > "
                #self.checkCmd()
            else:
                print msg["body"]
        else:
            print "Unknown message received from bridge > "
      
if __name__ == '__main__':
    a = BridgeControl()


