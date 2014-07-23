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

DISCOVER_TIME        = 10.0
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

    def sendParameter(self, parameter, data, timeStamp, a):
        msg = {"id": "zwave",
               "content": "parameter",
               "parameter": "switch",
               "data": data,
               "timeStamp": timeStamp}
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
                elif including:
                    URL = dataUrl + self.fromTime
            elif including:
                including = False
                URL = stopIncludeUrl
            elif self.exclude:
                if not excluding:
                    excluding = True
                    URL = startExcludeUrl
            elif excluding:
                excluding = False
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
                logging.debug("%s Could not load JSON in response", ModuleName)
            else:
                if dat:
                    if "updateTime" in dat:
                        self.fromTime = str(dat["updateTime"])
                    if self.include:
                        #logging.debug("%s include on, dat: %s", ModuleName, str(dat))
                        if "controller.data.lastIncludedDevice" in dat:
                            zid = dat["controller.data.lastIncludedDevice"]["value"]
                            if zid != "1":
                                included.append(zid)
                            logging.debug("%s %s Include list; %s", ModuleName, self.id, str(included))
                        if "controller.data.lastExcludedDevice" in dat:
                            zid = dat["controller.data.lastExcludedDevice"]["value"]
                            if zid != "1":
                                excluded.append(zid)
                            logging.debug("%s %s Excluded list; %s", ModuleName, self.id, str(excluded))
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
                                            elif j == "manufacturerId":
                                                manufacturer_name = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s %s manufacturer_name: %s", ModuleName, self.id, manufacturer_name) 
                                            elif j == "deviceTypeString":
                                                name = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s %s name: %s", ModuleName, self.id, name)
                                            elif j == "manufacturerProductType":
                                                model_number = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s %s model_number: %s", ModuleName, self.id, model_number)
                                    self.found.append({"protocol": "zwave",
                                                       "name": name,
                                                       #"mac_addr": "XXXXX" + str(d),
                                                       "mac_addr": str(d),
                                                       "manufacturer_name": manufacturer_name,
                                                       "model_number": model_number,
                                                       #"command_classes": command_classes
                                                     })
                                    # Stop discovery as soon as one new deivce has been included:
                                    reactor.callFromThread(self.stopDiscover)
                    else: # not including
                        #logging.debug("%s dat: %s", ModuleName, str(dat))
                        for g in self.getStrs:
                            if g.values()[0] in dat:
                                logging.debug("%s found: %s", ModuleName, g.keys()[0])
                                self.sendParameter("switch", dat[g.values()[0]], time.time(), g.keys()[0])
                time.sleep(MIN_DELAY)

    def sendDiscoverResults(self):
        d = {"status": "discovered",
             "id": "zwave",
             "body": self.found
            }
        logging.debug("%s sendDiscoveredResults: %s", ModuleName, d)
        self.cbSendManagerMsg(d)
        del self.found[:]
        self.discoveryResultsSent = True
 
    def stopDiscover(self):
        # Stop discovery after a fixed time if no new devices have been included
        logging.debug("%s stopDiscover", ModuleName)
        if not self.discoveryResultsSent:
            self.include = False
            reactor.callLater(MIN_DELAY, self.sendDiscoverResults)

    def discover(self):
        logging.debug("%s starting discovery", ModuleName)
        self.discoveryResultsSent = False
        self.include = True
        reactor.callLater(DISCOVER_TIME, self.stopDiscover)

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
                    ".commandClasses." + msg["commandClass"] + ".data." + msg["value"]
                getStr = {msg["id"]: g}
                logging.debug("%s New getStr: %s", ModuleName, getStr)
                self.getStrs.append(getStr)
                logging.debug("%s getStrs: %s", ModuleName, str(self.getStrs))
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
        elif cmd["cmd"] == "stop":
            msg = {"id": self.id,
                   "status": "stopping"}
            self.setState("stopping")
            reactor.callLater(2, self.doStop)
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
