#!/usr/bin/env python
#discovery.py

""" A very simple discovery program for BTLE devices.
    All it does it look for addresses and append them to a list. """

ModuleName = "Discovery           "

import sys
import time
import os
import json

if __name__ == '__main__':
    time.sleep(2)
    d = {}
    d["status"] = "discovered"
    d["devices"] = []
    d["devices"].append({"method": "btle",
                         "name": "SensorTag", 
                         "addr": "22.22.22.22.22.22"})
    d["devices"].append({"method": "btle",
                         "name": "SensorTag", 
                         "addr": "33.33.33.33.33.33"})
    d["devices"].append({"method": "btle",
                         "name": "SensorTag", 
                         "addr": "44.44.44.44.44.44"})
    print json.dumps(d)
