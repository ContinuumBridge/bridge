#!/usr/bin/env python
# zwavectrl_a.py
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

ZWAVE_DEVICES_FILE   = "zwave_devices.json"
DISCOVER_TIME        = 40.0
INCLUDE_WAIT_TIME    = 5.0
IPADDRESS            = 'localhost'
MIN_DELAY            = 1.0
PORT                 = "8083"
baseUrl              = "http://" + IPADDRESS + ":" + PORT +"/"
dataUrl              = baseUrl + 'ZWaveAPI/Data/'
startIncludeUrl      = baseUrl + "/ZWaveAPI/Run/controller.AddNodeToNetwork(1)"
stopIncludeUrl       = baseUrl + "/ZWaveAPI/Run/controller.AddNodeToNetwork(0)"
startExcludeUrl      = baseUrl + "/ZWaveAPI/Run/controller.RemoveNodeFromNetwork(1)"
stopExcludeUrl       = baseUrl + "/ZWaveAPI/Run/controller.RemoveNodeFromNetwork(0)"
postUrl              = baseUrl + "ZWaveAPI/Run/devices["
getURL               = baseUrl + "Run/devices[DDD].instances[III].commandClasses[CCC].Get()"
resetUrl             = baseUrl + "/ZWaveAPI/Run/SerialAPISoftReset()"
 
class ZwaveCtrl():
    def __init__(self, argv):
        procname.setprocname('cbzwavectrl')
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(levelname)s: %(message)s')
        self.status = "ok"
        self.state = "stopped"
        self.include = False
        self.exclude = False
        self.getting = False
        self.resetBoard = False
        self.getStrs = []
        self.cbFactory = {}
        self.adaptors = [] 
        self.found = []
        self.listen = []
        self.postToUrls = []
        if len(argv) < 3:
            logging.error("%s Improper number of arguments", ModuleName)
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        # Load zwave devices data
        self.zwave_devices = []    # In case file doesn't load
        try:
            with open(ZWAVE_DEVICES_FILE, 'r') as configFile:
                self.zwave_devices = json.load(configFile)
                logging.info('%s Read zwave devices file', ModuleName)
        except:
            logging.error('%s No zwave devices file exists or file is corrupt', ModuleName)
        self.fromTime = str(int(time.time()) - 1)
        logging.info("%s Hello", ModuleName)

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

    def sendParameter(self, data, timeStamp, a, commandClass, instance, value):
        msg = {"id": "zwave",
               "content": "data",
               "commandClass": commandClass,
               "instance": instance,
               "value": value,
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
        """ Include works as follow:
            Send the include URL. includeState = "waitInclude".
            Wait for the wait time. includeState = "waitInclude".
            Check if there's a new device there.
            If not wait again and repeat until time-out. includeState = "waitInclude".
            If there is check that vendor string is not null. includeState = "checkData"
            If it is wait and check again until time-out. includeState = "checkData"
            If vendor string is there, send information back to manager. includeState = "notIncluding"
            includeTick keeps tract of time in increments of INCLUDE_WAIT_TIME.
            Don't change the "from" time when getting data until all data has been retrieved.
        """
        includeState = "notIncluding"
        excludeState = "notExcluding"
        found = []
        h = httplib2.Http()
        posting = False
        error_count = 0
        while self.state != "stopping" and error_count < 4:
            if self.include:
                if includeState == "notIncluding":
                    foundDevice = False
                    foundData = False
                    losEndos = False
                    waitForVendorString = 0
                    nodeInfoFrameFound = False
                    includeState = "waitInclude"
                    incStartTime = str(int(time.time()))
                    includedDevice = ""
                    self.endMessage = "You should never see this message"
                    URL = startIncludeUrl
                    body = []
                    includeTick = 0
                    logging.debug("%s started including", ModuleName)
                elif includeState == "waitInclude":
                    #logging.debug("%s waitInclude, includeTick: %s foundData: %s", ModuleName, str(includeTick), foundData)
                    URL = dataUrl + incStartTime
                    if foundData:
                        includeState = "tidyUp"
                    elif foundDevice:
                        includeTick = 0
                        includeState = "checkData"
                        msg = {"id": self.id,
                               "status": "discovering"
                              }
                        reactor.callFromThread(self.cbSendManagerMsg, msg)
                    elif includeTick > 3:
                        self.endMessage = "No Z-Wave device found."
                        includeState = "tidyUp"
                    else:
                        includeTick += 1
                        time.sleep(INCLUDE_WAIT_TIME)
                elif includeState == "checkData":
                    logging.debug("%s checkData, includeTick: %s foundData %s", ModuleName, str(includeTick), foundData)
                    URL = dataUrl + incStartTime
                    if foundData:
                        includeState = "tidyUp"
                    elif includeTick > 4:
                        # Assume we're never going to get a vendorString and use zwave name
                        losEndos = True
                        includeState = "losEndos"
                    else:
                        includeTick += 1
                        time.sleep(INCLUDE_WAIT_TIME)
                elif includeState == "losEndos":
                    time.sleep(MIN_DELAY)
                    logging.debug("%s losEndos, foundData: %s", ModuleName, foundData)
                    losEndos = False
                    includeState = "tidyUp"
                elif includeState == "tidyUp":
                    logging.debug("%s tidyUp, includeTick: %s foundData %s", ModuleName, str(includeTick), foundData)
                    self.include = False
                    URL = stopIncludeUrl
                    includeState = "notIncluding"
                    reactor.callFromThread(self.stopDiscover)
                    time.sleep(INCLUDE_WAIT_TIME)
                else:
                    URL = stopIncludeUrl
                    includeState = "notIncluding"
            elif self.exclude:
                if excludeState == "notExcluding":
                    foundDevice = False
                    excludeState = "waitExclude"
                    incStartTime = str(int(time.time()))
                    excludedDevice = ""
                    URL = startExcludeUrl
                    excludeTick = 0
                    logging.debug("%s started excluding", ModuleName)
                elif excludeState == "waitExclude":
                    logging.debug("%s waitExclude, excludeTick: %s", ModuleName, str(excludeTick))
                    URL = dataUrl + incStartTime
                    if foundDevice or excludeTick > 4:
                        excludeState = "notExcluding"
                        self.exclude = False
                        msg = {"id": self.id,
                               "status": "excluded",
                               "body": excludedDevice
                              }
                        reactor.callFromThread(self.cbSendManagerMsg, msg)
                        URL = stopExcludeUrl       
                    else:
                        excludeTick += 1
                        time.sleep(INCLUDE_WAIT_TIME)
            elif self.resetBoard:
                URL = resetUrl
                reactor.callFromThread(self.setState, "stopping")
                self.resetBoard = False
                logging.debug("%s Resetting RazBerry board", ModuleName)
            elif self.postToUrls:
                posting = True
                URL = self.postToUrls.pop() 
            elif self.getting:
                self.getting = False
            else:
                URL = dataUrl + self.fromTime
            #logging.debug("%s URL: %s", ModuleName, URL)
            try:
                resp, content = h.request(URL,
                                         'POST',
                                          headers={'Content-Type': 'application/json'})
            except Exception as ex:
                error_count += 1
                logging.error('%s error in accessing z-way. URL: %s, error_count: %s', ModuleName, URL, str(error_count))
                logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            else:
                error_count = 0
                if "value" in resp:
                    if resp["value"] != "200":
                        logging.debug("%s non-200 response: %s", ModuleName, resp["value"])
            try:
                dat = json.loads(content)
            except:
                logging.warning("%s Could not load JSON in response, content: %s, URL: %s", ModuleName, str(content), URL)
                self.fromTime = time.time() - 1
            else:
                if dat:
                    if "updateTime" in dat:
                        self.fromTime = str(dat["updateTime"])
                    if self.exclude:
                        if "controller.data.lastExcludedDevice" in dat:
                            excludedDevice = str(dat["controller.data.lastExcludedDevice"]["value"])
                            if excludedDevice != "None" and excludedDevice != 0:
                                logging.debug("%s found excludedDevice; %s", ModuleName, excludedDevice)
                                foundDevice = True
                            logging.debug("%s lastExcludedDevice; %s", ModuleName, excludedDevice)
                    if self.include:
                        #logging.debug("%s including. dat: %s", ModuleName, dat)
                        if "controller.data.lastIncludedDevice" in dat:
                            includedDevice = str(dat["controller.data.lastIncludedDevice"]["value"])
                            if includedDevice != "None":
                                foundDevice = True
                            logging.debug("%s %s includedDevice %s", ModuleName, self.id, includedDevice)
                        if "devices" in dat:
                            logging.debug("%s devices in dat", ModuleName)
                            for d in dat["devices"].keys():
                                logging.debug("%s device: %s", ModuleName, d)
                                if d == includedDevice:
                                    for k in dat["devices"][d].keys():
                                        for j in dat["devices"][d][k].keys():
                                            if j == "nodeInfoFrame":
                                                command_classes = dat["devices"][d][k][j]["value"]
                                                nodeInfoFrameFound = True
                                                logging.debug("%s command_classes: %s", ModuleName, command_classes)
                                            elif j == "vendorString":
                                                vendorString = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s vendorString: %s", ModuleName, vendorString) 
                                            elif j == "deviceTypeString":
                                                deviceTypeString = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s zwave name: %s", ModuleName, deviceTypeString)
                                            elif j == "manufacturerProductId":
                                                manufacturerProductId = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s manufacturerProductId: %s", ModuleName, manufacturerProductId)
                                            elif j == "manufacturerProductType":
                                                manufacturerProductType = dat["devices"][d][k][j]["value"]
                                                logging.debug("%s manufacturerProductType : %s", ModuleName, manufacturerProductType)
                                    if nodeInfoFrameFound and not foundData:
                                        if vendorString == "":
                                            if waitForVendorString == 3:
                                                logging.debug("%s found device with no vendorString", ModuleName)
                                                for dev in self.zwave_devices:
                                                    logging.debug("%s found device: %s", ModuleName, str(command_classes))
                                                    logging.debug("%s comparing found device to : %s", ModuleName, str(dev))
                                                    if str(command_classes) != None:
                                                        if len(dev["command_classes"]) != len(command_classes):
                                                            logging.debug("%s lengths do not match", ModuleName)
                                                            found = False
                                                        else:
                                                            logging.debug("%s lengths match", ModuleName)
                                                            found = True
                                                            for c in dev["command_classes"]:
                                                                logging.debug("%s command_class : %s", ModuleName, str(c))
                                                                if c not in command_classes:
                                                                    found = False
                                                                    break
                                                            if found:
                                                                name = dev["name"]
                                                                logging.debug("%s matched device. name : %s", ModuleName, name)
                                                                self.endMessage = "Found Z-Wave device: " + name
                                                                break
                                                    else:
                                                        logging.debug("%s Incomplete Z-Wave interview", ModuleName)
                                                        self.endMessage = "Problem interviewing Z-Wave device. Please Z-exclude & try again"
                                                if not found:
                                                    logging.debug("%s not found", ModuleName)
                                                    name = ""
                                                    self.endMessage = "No known Z-Wave device found"
                                                foundData = True
                                            else:
                                                waitForVendorString += 1
                                        else:
                                            name = vendorString + " " + str(manufacturerProductId) + " " + str(manufacturerProductType)
                                            logging.debug("%s found device with vendorString: %s", ModuleName, name)
                                            self.endMessage = "Found Z-Wave device: " + name
                                            foundData = True
                                        if foundData:
                                            logging.debug("%s found name: %s", ModuleName, name)
                                            self.found.append({"protocol": "zwave",
                                                               "name": name,
                                                               #"mac_addr": "XXXXX" + str(d),
                                                               "address": str(d),
                                                               "manufacturer_name": vendorString,
                                                               "model_number": manufacturerProductId,
                                                               #"command_classes": command_classes
                                                              })
                    else: # not including
                        #logging.debug("%s dat: %s", ModuleName, str(dat))
                        for g in self.getStrs:
                            if g["match"] in dat:
                                #logging.debug("%s found: %s %s", ModuleName, g["address"], g["commandClass"])
                                self.sendParameter(dat[g["match"]], time.time(), g["address"], g["commandClass"], g["instance"], g["value"])
            if posting:
                posting = False
            else:
                time.sleep(MIN_DELAY)

    def sendUserMessage(self):
        msg = {"id": self.id,
                "status": "user_message",
                "body": self.endMessage
               }
        self.cbSendManagerMsg(msg)

    def stopDiscover(self):
        self.include = False
        d = {"status": "discovered",
             "id": "zwave",
             "body": self.found
            }
        logging.debug("%s sendDiscoveredResults: %s", ModuleName, d)
        self.cbSendManagerMsg(d)
        reactor.callLater(1.0, self.sendUserMessage)
        del self.found[:]

    def discover(self):
        logging.debug("%s starting discovery", ModuleName)
        self.include = True

    def startExclude(self):
        logging.debug("%s starting exclude", ModuleName)
        self.exclude = True

    def onAdaptorMessage(self, msg):
        #logging.debug("%s onAdaptorMessage: %s", ModuleName, msg)
        if "request" in msg:
            if msg["request"] == "init":
                resp = {"id": "zwave",
                        "content": "init"}
                self.sendMessage(resp, msg["id"])
            elif not "address" in msg:
                logging.warning("%s Message received with no address: %s", ModuleName, str(msg))
            elif msg["request"] == "check":
                postToUrl = postUrl + msg["address"] + "].SendNoOperation()"
                #logging.debug("%s postToUrl: %s", ModuleName, str(postToUrl))
                self.postToUrls.insert(0, postToUrl)
            elif msg["request"] == "force_interview":
                postToUrl = postUrl + msg["address"] + "].InterviewForce()"
                #logging.debug("%s postToUrl: %s", ModuleName, str(postToUrl))
                self.postToUrls.insert(0, postToUrl)
            elif not "instance" in msg or not "commandClass" in msg:
                logging.warning("%s instance and commandClass expected in msg: %s", ModuleName, str(msg))
            elif msg["request"] == "getc":
                g = "devices." + msg["address"] + ".data.isFailed"
                getStr = {"address": msg["id"],
                          "match": g, 
                          "commandClass": msg["commandClass"],
                          "value": "",
                          "instance": msg["instance"]
                         }
                logging.debug("%s New getStr (check): %s", ModuleName, str(getStr))
                self.getStrs.append(getStr)
            elif msg["request"] == "get":
                g = "devices." + msg["address"] + ".instances." + msg["instance"] + \
                    ".commandClasses." + msg["commandClass"] + ".data"
                if "value" in msg:
                    g += "." + msg["value"]
                    value = msg["value"]
                else: 
                    value = ""
                if "name" in msg:
                    g += "." + msg["name"]
                getStr = {"address": msg["id"],
                          "match": g, 
                          "commandClass": msg["commandClass"],
                          "value": value,
                          "instance": msg["instance"]
                         }
                logging.debug("%s New getStr: %s", ModuleName, str(getStr))
                self.getStrs.append(getStr)
                #logging.debug("%s getStrs: %s", ModuleName, str(self.getStrs))
            elif not "action" in msg or not "value" in msg:
                logging.warning("%s action and value expected in post msg: %s", ModuleName, str(msg))
            elif msg["request"] == "post":
                postToUrl = postUrl + msg["address"] + "].instances[" + msg["instance"] + \
                            "].commandClasses[" + msg["commandClass"] + "]." + msg["action"] + "(" + \
                            msg["value"] + ")"
                #logging.debug("%s postToUrl: %s", ModuleName, str(postToUrl))
                self.postToUrls.insert(0, postToUrl)
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
                    self.listen.append(reactor.listenUNIX(a["socket"], self.cbFactory[a["id"]]))
        # Start zway even if there are no zway devices, in case we want to discover some
        reactor.callInThread(self.zway)

    def doStop(self):
        # Stop listening on all ports (to prevent nasty crash on exit)
        for l in self.listen:
            l.stopListening()
        try:
            reactor.stop()
        except:
            logging.warning("%s %s stopReactor when reactor not running", ModuleName, self.id)
        logging.info("%s Bye from %s", ModuleName, self.id)
        sys.exit

    def onManagerMessage(self, cmd):
        logging.debug("%s Received from manager: %s", ModuleName, cmd)
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
            # Reset Razberry board before stopping
            self.resetBoard = True
            reactor.callLater(2.5, self.doStop)
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
