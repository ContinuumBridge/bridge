#!/usr/bin/env python
# uwe_example.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
import httplib2
from datetime import datetime
import json
import time
from pprint import pprint
import thread

doStop = False

def getCmd():
    global doStop
    cmd = raw_input("Type any key to stop")
    doStop = True
    return True

thread.start_new_thread(getCmd, ())

ipAddress = "192.168.0.12"
port = "8880"
baseUrl = "http://" + ipAddress + ":" + port +"/"
configUrl = baseUrl + "config"
deviceUrl = baseUrl + "device"

# Enable output of values
config = {"enable": "True"}
configData = json.dumps(config)
URL = configUrl
h = httplib2.Http()
resp, content = h.request(URL,
                          'POST',
                          configData,
                          headers={'Content-Type': 'application/json'})
print ""
pprint(resp)
pprint(json.loads(content))
print ""
print ""

# Get config information from the bridge
URL = configUrl
resp, content = h.request(URL,
                          'GET',
                          headers={'Content-Type': 'application/json'})
pprint(resp)
pprint(json.loads(content))
config = json.loads(content)
idToName = config["config"]["idToName"]     
print "idToName: ", idToName
print ""

devices = []
for d in config["config"]["services"]:
    devices.append(d["id"])
print "devices:", devices

while not doStop:
    for devID in devices: 
        URL = deviceUrl + "/" + devID
        h = httplib2.Http()
        resp, content = h.request(URL,
                                  'GET',
                                  headers={'Content-Type': 'application/json'})
        #pprint(resp)
        bridgeData = json.loads(content)
        #pprint(json.loads(content))
        for d in bridgeData["data"]:
            if d["type"] == "temp":
                localTime = time.localtime(d["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                dat = now +\
                    "   " + idToName[bridgeData["device"]] + \
                    " temp = " + \
                    str("%4.1f" %d["data"]) 
                print dat
            elif d["type"] == "buttons":
                localTime = time.localtime(d["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                dat = now +\
                    "   " + idToName[bridgeData["device"]] + \
                    " buttons = left: " + \
                    str(d["data"]["leftButton"]) + \
                    " right " + str(d["data"]["rightButton"])
                print dat

# Disable output of values
config = {"enable": False}
configData = json.dumps(config)
URL = configUrl
h = httplib2.Http()
resp, content = h.request(URL,
                          'POST',
                          configData,
                          headers={'Content-Type': 'application/json'})
print ""
pprint(resp)
