#!/usr/bin/env python
# eew_test.py
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
import sys
import thread

if len(sys.argv) < 2:
    print "Usage: manager <bridge ip address>:<bridge socket>"
    exit(1)
ipAddress = sys.argv[1]
port = "8881"

doStop = False

def getCmd():
    global doStop
    cmd = raw_input("Press return to stop")
    doStop = True
    return True

thread.start_new_thread(getCmd, ())

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

# Parse servies to find what devices are present & add these to our list
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
        #pprint(bridgeData)
        for d in bridgeData["data"]:
            if d["type"] == "temperature":
                localTime = time.localtime(d["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                dat = now +\
                    "   " + idToName[bridgeData["device"]] + \
                    " temp  =  " + \
                    str("%4.1f" %d["data"]) 
                print dat
            elif d["type"] == "ir_temperature":
                localTime = time.localtime(d["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                dat = now +\
                    "   " + idToName[bridgeData["device"]] + \
                    " ir_temp  =  " + \
                    str("%4.1f" %d["data"]) 
                print dat
            elif d["type"] == "rel_humidity":
                localTime = time.localtime(d["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                dat = now +\
                    "   " + idToName[bridgeData["device"]] + \
                    " rel H    =  " + \
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
            elif d["type"] == "accel":
                localTime = time.localtime(d["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                dat = now +\
                    "   " + idToName[bridgeData["device"]] + \
                    " accel = " + str("%2.2f" %d["data"][0]) + \
                    "  " + str("%2.2f" %d["data"][1]) + \
                    "  " + str("%2.2f" %d["data"][2])
                print dat
            elif d["type"] == "gyro":
                localTime = time.localtime(d["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                dat = now +\
                    "   " + idToName[bridgeData["device"]] + \
                    " gyro  = " + str("%5.2f" %d["data"][0]) + \
                    "  " + str("%5.2f" %d["data"][1]) + \
                    "  " + str("%5.2f" %d["data"][2])
                print dat
            elif d["type"] == "magnetometer":
                localTime = time.localtime(d["timeStamp"])
                now = time.strftime("%H:%M:%S", localTime)
                dat = now +\
                    "   " + idToName[bridgeData["device"]] + \
                    " mag   = " + str("%5.2f" %d["data"][0]) + \
                    "  " + str("%5.2f" %d["data"][1]) + \
                    "  " + str("%5.2f" %d["data"][2])
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
