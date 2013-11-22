#!/usr/bin/env python
#discovery.py

""" A very simple discovery program for BTLE devices.
    All it does it look for addresses and append them to a list. """

ModuleName = "Discovery           "

import sys
import time
import os
import pexpect
import json
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor, defer
from twisted.internet import task

if __name__ == '__main__':
    discoveredAddresses = []
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

    d = {}
    d["status"] = "discovered"
    d["devices"] = []
    for a in range (len(discoveredAddresses)):
        d["devices"].append({"method": "btle",
                             "name": "SensorTag", 
                             "addr": discoveredAddresses[a]})
    print json.dumps(d)
