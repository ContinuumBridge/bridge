#!/usr/bin/env python
# tempo.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "z-wave_ctrl"

import sys
import time
import os
import json
import httplib2
import logging
import procname
from pprint import pprint
from cbconfig import *
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import defer
from twisted.internet import reactor
from twisted.internet.task import deferLater
from cbcommslib import CbClientProtocol
from cbcommslib import CbClientFactory
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory

DISCOVER_TIME        = 26.0
DISCOVER_WAIT_TIME   = 18.0
IPADDRESS            = 'localhost'
MIN_DELAY            = 1.0
PORT                 = "8083"
baseUrl              = "http://" + IPADDRESS + ":" + PORT +"/"
dataUrl              = baseUrl + 'ZWaveAPI/Data/'
startIncludeUrl      = baseUrl + "/ZWaveAPI/Run/controller.AddNodeToNetwork(1)"
stopIncludeUrl       = baseUrl + "/ZWaveAPI/Run/controller.AddNodeToNetwork(0)"
startExcludeUrl      = baseUrl + "/ZWaveAPI/Run/controller.RemoveNodeFromNetwork(1)"
stopExcludeUrl       = baseUrl + "/ZWaveAPI/Run/controller.RemoveNodeFromNetwork(0)"
postUrl              = baseUrl + "ZwaveAPI/Run/devices["
getURL               = baseUrl + "Run/devices[DDD].instances[III].commandClasses[CCC].Get()"
 
class ZwaveCtrl():
    def __init__(self, argv):
        procname.setprocname('cbzwavectrl')
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.status = "ok"
        self.state = "stopped"
        self.include = False
        self.exclude = False
        self.posting = False
        self.getting = False
        self.getStrs = []
        self.cbFactory = {}
        self.adaptors = [] 
        self.found = []
        if len(argv) < 3:
            logging.error("%s Improper number of arguments", ModuleName)
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        logging.info("%s Hello", ModuleName)

       
        self.fromTime = str(int(time.time()) - 1)

        # Connection to manager
        initMsg = {"id": self.id,
                   "type": "zwave",
                   "status": "req-config"} 
        self.managerFactory = CbClientFactory(self.onManagerMessage, initMsg)
        self.managerConnect = reactor.connectUNIX(managerSocket, self.managerFactory, timeout=10)
        reactor.run()
 
    def sendMessage(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def cbSendManagerMsg(self, msg):
        self.managerFactory.sendMsg(msg)

    def setState(self, action):
        self.state = action
        logging.debug("%s %s state = %s", ModuleName, self.id, self.state)
        msg = {"id": self.id,
               "status": "state",
               "state": self.state}
        self.cbSendManagerMsg(msg)

    def sendParameter(self, data, timeStamp, a, commandClass):
        msg = {"id": "zwave",
               "content": "data",
               "commandClass": commandClass,
               "data": data,
               "timeStamp": timeStamp}
        #logging.debug("%s sendParameter: %s %s", ModuleName, str(msg), a)
        reactor.callFromThread(self.sendMessage, msg, a)

    def checkAllProcessed(self, appID):
        self.processedApps.append(appID)
        found = True
        for a in self.appInstances:
            if a not in self.processedApps:
                found = False
        if found:
            self.setState("inUse")

    def zway(self):
        including = False
        excluding = False
        included = []
        excluded = []
        found = []
        h = httplib2.Http()
        while self.state != "stopping":
            if self.include:
                if not including:
                    including = True
                    del included[:]
                    URL = startIncludeUrl
                    body = []
                    logging.debug("%s started including", ModuleName)
                elif including:
                    # To prevent problems with getting half-updated information from z-way
                    # Give enough time to press button & get all data from device
                    logging.debug("%s about to sleep", ModuleName)
                    time.sleep(DISCOVER_WAIT_TIME)
                    logging.debug("%s stopped sleeping", ModuleName)
                    URL = dataUrl + self.fromTime
            elif including:
                including = False
                URL = stopIncludeUrl
            elif self.exclude:
                if not excluding:
                    excluding = True
                    del excluded[:]
                    URL = startExcludeUrl
                    logging.debug("%s started excluding", ModuleName)
            elif excluding:
                logging.debug("%s stopping excluding", ModuleName)
                excluding = False
                if excluded:
                    if excluded[0] == "None":
                        self.excludeResult = "Unidentified device"
                    else:
                        self.excludeResult = excluded
                else:
                    self.excludeResult = "No devices were excluded"
                URL = stopExcludeUrl
            elif self.posting:
                self.posting = False
                URL = self.postToUrl 
            elif self.getting:
                self.getting = False
            else:
                URL = dataUrl + self.fromTime
            #logging.debug("%s URL: %s", ModuleName, URL)
            resp, content = h.request(URL,
                                     'POST',
                                      headers={'Content-Type': 'application/json'})
            if "value" in resp:
                if resp["value"] != "200":
                    logging.debug("%s non-200 response: %s", ModuleName, resp["value"])
            try:
                dat = json.loads(content)
            except:
                logging.debug("%s Could not load JSON in response: %s", ModuleName, str(content))
            else:
                if dat:
                    if "updateTime" in dat:
                        self.fromTime = str(dat["updateTime"])
                    if self.exclude:
                        if "controller.data.lastExcludedDevice" in dat:
                            logging.debug("%s lastExcludedDevice; %s", ModuleName, str(dat["controller.data.lastExcludedDevice"]))
                            zid = dat["controller.data.lastExcludedDevice"]["value"]
                            if zid != 1:
                                excluded.append(zid)
                            logging.debug("%s %s Excluded list; %s", ModuleName, self.id, str(excluded))
                    if self.include:
                        if "controller.data.lastIncludedDevice" in dat:
                            zid = dat["controller.data.lastIncludedDevice"]["value"]
                            if zid != 1:
                                included.append(zid)
                            logging.debug("%s %s Include list; %s", ModuleName, self.id, str(included))
                        if "updateTime" in dat:
                            self.fromTime = str(dat["updateTime"])
                        if "devices" in dat:
                            logging.debug("%s devices in dat", ModuleName)
                            devs = "Included devices: "
                            for d in dat["devices"].keys():
                                devs += d + " "
                                logging.debug("%s %s Included devices: %s", ModuleName, self.id, devs)
                                new = False
                                if d != "1":
                                    new = True
                                    for a in self.adaptors:
                                        if d == a["address"]:
                                            new = False
                                            break
                                    for a in self.found:
                                        #if d == a["mac_addr"][5:]:
                                        if d == a["mac_addr"]:
                                            new = False
                                            break
                                if new:
                                    for k in dat["devices"][d].keys():
                                        for j in dat["devices"][d][k].keys():
                                            if j == "nodeInfoFrame":
                                                command_classes = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s %s command_classes: %s", ModuleName, self.id, command_classes)
                                            elif j == "vendorString":
                                                manufacturer_name = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s %s manufacturer_name: %s", ModuleName, self.id, manufacturer_name) 
                                            elif j == "deviceTypeString":
                                                deviceTypeString = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s %s zwave name: %s", ModuleName, self.id, deviceTypeString)
                                            elif j == "manufacturerProductId":
                                                model_number = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s %s model_number: %s", ModuleName, self.id, model_number)
                                    if manufacturer_name == "":
                                        name = deviceTypeString
                                    else:
                                        name = manufacturer_name + " " + str(model_number)
                                    logging.debug("%s %s name: %s", ModuleName, self.id, name)
                                    self.found.append({"protocol": "zwave",
                                                       "name": name,
                                                       #"mac_addr": "XXXXX" + str(d),
                                                       "mac_addr": str(d),
                                                       "manufacturer_name": manufacturer_name,
                                                       "model_number": model_number,
                                                       #"command_classes": command_classes
                                                     })
                                    # Stop discovery as soon as one new deivce has been included:
                                    self.discTime = time.time()
                                    reactor.callFromThread(self.stopDiscover)
                                    self.debugTime = self.fromTime
                                    self.debugDat = dat
                                    self.debugContent = content
                                    #reactor.callFromThread(self.debugPrint)
                    else: # not including
                        #logging.debug("%s dat: %s", ModuleName, str(dat))
                        for g in self.getStrs:
                            if g["match"] in dat:
                                #logging.debug("%s found: %s %s", ModuleName, g["address"], g["commandClass"])
                                self.sendParameter(dat[g["match"]], time.time(), g["address"], g["commandClass"])
                time.sleep(MIN_DELAY)

    def debugPrint(self):
        reactor.callInThread(self.dodebugPrint)

    def dodebugPrint(self):
        print "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        print "updateTime: ", self.debugTime
        pprint(self.debugDat)

    def stopDiscover(self):
        # Stop discovery after a fixed time if no new devices have been included
        logging.debug("%s stopDiscover, discoveryResultsSent: %s", ModuleName, self.discoveryResultsSent)
        self.include = False
        if not self.discoveryResultsSent:
            self.discoveryResultsSent = True
            d = {"status": "discovered",
                 "id": "zwave",
                 "body": self.found
                }
            logging.debug("%s sendDiscoveredResults: %s", ModuleName, d)
            self.cbSendManagerMsg(d)
            del self.found[:]

    def discover(self):
        logging.debug("%s starting discovery", ModuleName)
        self.discTime = time.time()
        self.discoveryResultsSent = False
        self.include = True
        reactor.callLater(DISCOVER_TIME, self.stopDiscover)

    def stopExclude(self):
        self.exclude = False
        msg = {"id": self.id,
               "status": "excluded",
               #"body": "Z-wave devices excluded: " + self.excludeResult}
               "body": "Z-wave devices excluded: not available at this release"}
        self.cbSendManagerMsg(msg)

    def startExclude(self):
        logging.debug("%s starting exclude", ModuleName)
        self.excludeResult = "none"
        self.excluded = []
        self.exclude = True
        reactor.callLater(DISCOVER_TIME, self.stopExclude)

    def onAdaptorMessage(self, msg):
        logging.debug("%s onAdaptorMessage: %s", ModuleName, msg)
        if "request" in msg:
            if msg["request"] == "init":
                resp = {"id": "zwave",
                        "content": "init"}
                self.sendMessage(resp, msg["id"])
            elif msg["request"] == "post":
                self.postToUrl = postUrl + msg["address"] + "].instances[" + msg["instance"] + \
                                 "].commandClasses[" + msg["commandClass"] + "]." + msg["action"] + "(" + \
                                 msg["value"] + ")"
                logging.debug("%s postToUrl: %s", ModuleName, str(self.postToUrl))
                self.posting = True
            elif msg["request"] == "get":
                g = "devices." + msg["address"] + ".instances." + msg["instance"] + \
                    ".commandClasses." + msg["commandClass"] + ".data"
                if "value" in msg:
                    g += "." + msg["value"]
                getStr = {"address": msg["id"],
                          "match": g, 
                          "commandClass": msg["commandClass"]
                         }
                logging.debug("%s New getStr: %s", ModuleName, str(getStr))
                self.getStrs.append(getStr)
                #logging.debug("%s getStrs: %s", ModuleName, str(self.getStrs))
        else:
            logging.debug("%s onAdaptorMessage without request: %s", ModuleName, str(msg))

    def processConfig(self, config):
        logging.debug("%s processConf: %s", ModuleName, config)
        if config != "no_zwave":
            for a in config:
                if a["id"] not in self.adaptors:
                    # Allows for reconfig on the fly
                    self.adaptors.append({"adt": a["id"],
                                          "address": a["address"]
                                        })
                    self.cbFactory[a["id"]] = CbServerFactory(self.onAdaptorMessage)
                    reactor.listenUNIX(a["socket"], self.cbFactory[a["id"]])
        # Start zway even if there are no zway devices, in case we want to discover some
        reactor.callInThread(self.zway)

    def doStop(self):
        try:
            reactor.stop()
        except:
            logging.warning("%s %s stopReactor when reactor not running", ModuleName, self.id)
        logging.info("%s Bye from %s", ModuleName, self.id)
        sys.exit

    def onManagerMessage(self, cmd):
        #logging.debug("%s Received from manager: %s", ModuleName, cmd)
        if cmd["cmd"] == "discover":
            self.discover()
            msg = {"id": self.id,
                   "status": "ok"}
        elif cmd["cmd"] == "exclude":
            self.startExclude()
            msg = {"id": self.id,
                   "status": "ok"}
        elif cmd["cmd"] == "stop":
            msg = {"id": self.id,
                   "status": "stopping"}
            self.setState("stopping")
            reactor.callLater(1.5, self.doStop)
        elif cmd["cmd"] == "config":
            self.processConfig(cmd["config"])
            msg = {"id": self.id,
                   "status": "ready"}
        else:
            msg = {"id": self.id,
                   "status": "ok"}
        self.cbSendManagerMsg(msg)

if __name__ == '__main__':
    zwaveCtrl = ZwaveCtrl(sys.argv)
