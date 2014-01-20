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
#from twisted.internet.protocol import Protocol, Factory
#from twisted.internet import reactor, defer
#from twisted.internet import task

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print ModuleName, "Usage: discover <protocol> <sim>"
        exit(1)
    protocol = sys.argv[1]
    sim = sys.argv[2]
    discoveredAddresses = []
    if sim == "0":
        try:
            os.system("sudo hciconfig hci0 up")
        except:
            print ModuleName, "Unable to bring up hci0 interface"
        try:
            cmd = "sudo hcitool lescan"
            p = pexpect.spawn(cmd)
        except:
            sys.stderr.write(ModuleName + "Error: lescan failed to spawn\n")
            sys.exit()
        try:
            p.expect('.*', timeout=10)
            p.expect('.*', timeout=10)
        except:
            sys.stderr.write(ModuleName + "Error. Nothing returned from pexpect\n")
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
                else:
                    for a in discoveredAddresses:
                        if addr == a:
                            found = True
                    if found == False:
                        discoveredAddresses.append(addr)
            except:
                sys.stderr.write(ModuleName + "lescan skip \n")
        try:
            p.sendcontrol("c")
        except:
            sys.stderr.write(ModuleName + "Error: Could not kill lescan process\n")
    else: 
        # Simulation without real devices - just supply some sample data
        discoveredAddresses = ["22.22.22.22.22.22", "33.33.33.33.33.33", "44.44.44.44.44.44"]
    d = {}
    d["status"] = "discovered"
    d["body"] = []
    for a in range (len(discoveredAddresses)):
        d["body"].append({"protocol": "btle",
                          "name": "SensorTag", 
                          "mac_addr": discoveredAddresses[a]})
    print json.dumps(d)
