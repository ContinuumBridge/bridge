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
    d["num"] = 2
    for a in range (2):
        d[0] = ["SensorTag", "22.22.22.22.22.22"]
        d[1] = ["SensorTag", "33.33.33.33.33.33"]
    print json.dumps(d)
