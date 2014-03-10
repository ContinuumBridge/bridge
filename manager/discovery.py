#!/usr/bin/env python
# discovery.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#

""" A very simple discovery program for BTLE devices.
    All it does it look for addresses and append them to a list. """

ModuleName = "Discovery            "

import sys
import time
import os
import pexpect
import json

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print ModuleName, "Usage: discover <protocol> <sim> <CB_CONFIG_DIR>"
        exit(1)
    protocol = sys.argv[1]
    sim = sys.argv[2]
    CB_CONFIG_DIR = sys.argv[3]
    if sim == "1":
        discoverySimFile = CB_CONFIG_DIR + 'discovery.sim'
        with open(discoverySimFile, 'r') as f:
            s = f.read()
        if s.endswith('\n'):
            s = s[:-1]
        simStep = int(s)
    discoveredAddresses = []
    names = []
    manufacturers = []
    protocols = []
    if sim == "0":
        try:
            os.system("sudo hciconfig hci0 up")
        except:
            #print ModuleName, "Unable to bring up hci0 interface"
            d = {"status": "error"}        
            print json.dumps(d)
            sys.exit()
        try:
            cmd = "sudo hcitool lescan"
            p = pexpect.spawn(cmd)
        except:
            sys.stderr.write(ModuleName + "Error: lescan failed to spawn\n")
            d = {"status": "error"}        
            print json.dumps(d)
            sys.exit()
        try:
            p.expect('.*', timeout=10)
            p.expect('.*', timeout=10)
        except:
            sys.stderr.write(ModuleName + "Error. Nothing returned from pexpect\n")
            d = {"status": "error"}        
            print json.dumps(d)
            sys.exit()
        startTime = time.time()
        endTime = startTime + 10
        while time.time() < endTime:
            try:
                p.expect('.*', timeout=10)
                raw = p.after.split()
                addr = raw[0]
                found = False
                if len(discoveredAddresses) == 0:
                    discoveredAddresses.append(addr)
                    names.append("SensorTag")
                    manufacturers.append("Texas Instruments")
                else:
                    for a in discoveredAddresses:
                        if addr == a:
                            found = True
                    if found == False:
                        discoveredAddresses.append(addr)
                        names.append("SensorTag")
                        manufacturers.append("Texas Instruments")
            except:
                sys.stderr.write(ModuleName + "lescan skip \n")
        try:
            p.sendcontrol("c")
        except:
            sys.stderr.write(ModuleName + "Error: Could not kill lescan process\n")
    else: 
        # Simulation without real devices - just supply some sample data
        names = ["SensorTag", "SensorTag", "SensorTag"]
        manufacturers = ["Texas Instruments", "Texas Instruments", "Shenzhen Youhong Technology Co."]
        protocols = ["btle", "btle", "btle"]
        if simStep == 0:
            discoveredAddresses = ["22.22.22.22.22.22"]
        elif simStep == 1:
            discoveredAddresses = ["33.33.33.33.33.33"]
        elif simStep == 2:
            discoveredAddresses = ["44.44.44.44.44.44"]
        elif simStep == 3:
            discoveredAddresses = ["55.55.55.55.55.55", "66.66.66.66.66.66"]
        elif simStep == 4:
            discoveredAddresses = ["66.66.66.66.66.66"]
        elif simStep == 5:
            discoveredAddresses = ["77.77.77.77.77.77", "88.88.88.88.88.88", "99.99.99.99.99.99"]
        elif simStep == 6:
            discoveredAddresses = ["88.88.88.88.88.88", "99.99.99.99.99.99"]
        simStep += 1
        f = open(discoverySimFile, 'w')
        f.write(str(simStep) + '\n')
        f.close()
    d = {}
    d["status"] = "discovered"
    d["body"] = []
    for a in range (len(discoveredAddresses)):
        d["body"].append({"protocol": "btle",
                          "name": names[a], 
                          "manufacturer_name": manufacturers[a], 
                          "protocol": protocols[a],
                          "mac_addr": discoveredAddresses[a]})
    print json.dumps(d)
