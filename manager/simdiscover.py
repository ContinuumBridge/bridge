#!/usr/bin/env python
# simdiscover.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
# Provides simulated values for discovered devices

class SimDiscover():
    def __init__(self, bridge_id):
        self.bridge_id = bridge_id
        self.step = 0

    def discover(self, isotime):
        d = {}
        d["source"] = self.bridge_id
        d["destination"] = "cb"
        d["time_sent"] = isotime
        d["body"] = {}
        d["body"]["resource"] = "/api/bridge/v1/discovered_device/"
        d["body"]["verb"] = "patch"
        d["body"]["objects"] = []
        if self.step == 0:
            b = {'manufacturer_name': '',
                 'protocol': 'peripheral',
                 'address': '0',
                 'name': 'km_gpio_adaptor'
                }
            d["body"]["objects"].append(b)
        if self.step == 1:
            b = {'manufacturer_name': 'Hostmann Controls',
                 'protocol': 'zwave',
                 'address': '40',
                 'name': 'Hostmann Controls 1 3',
                 'product_id': 1,
                 'product_type': 3,
                 'command_classes': [114, 134, 64, 37]
                }
            d["body"]["objects"].append(b)
        elif self.step == 2:
            b = {'manufacturer_name': 'Texas Instruments',
                 'protocol': 'ble',
                 'address': "22.22.22.22.22.22",
                 'name': 'Continuum'
                }
            d["body"]["objects"].append(b)
        elif self.step == 3:
            b = {'manufacturer_name': 'Texas Instruments',
                 'protocol': 'ble',
                 'address': "33.33.33.33.33.33",
                 'name': 'Continuum'
                }
            d["body"]["objects"].append(b)
            b = {'manufacturer_name': 'Texas Instruments',
                 'protocol': 'ble',
                 'address': "44.44.44.44.44.44",
                 'name': 'Continuum'
                }
            d["body"]["objects"].append(b)
        elif self.step == 4:
            b = {'manufacturer_name': 'Temper',
                 'protocol': 'usb',
                 'address': "007",
                 'name': 'TEMPer1'
                }
            d["body"]["objects"].append(b)
        self.step = (self.step + 1) % 6
        return d

if __name__ == '__main__':
     import json
     s = SimDiscover("BID1")
     for i in range(0, 7):
         d = s.discover(1234567)
         print(json.dumps(d, indent=4))
