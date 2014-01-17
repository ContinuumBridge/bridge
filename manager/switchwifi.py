#!/usr/bin/env python
# switchwifi.py
# Copyright (C) ContinuumBridge Limited, 2013 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#

""" Switches wlan0 between being an access point and a client """

ModuleName = "Switch WiFi          "

import sys
import time
import os
import pexpect

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print "Usage: switchwifi [client|server]"
        exit(1)
    switchTo = sys.argv[1]

    if switchTo == "server":
        os.system("ifdown wlan0")
        print ModuleName, "wlan0 down"
        os.system("killall wpa_supplicant")
        print ModuleName, "wpa_supplicant process killed"
        os.system("cp interfaces.server /etc/network/interfaces")
        os.system("ifup wlan0")
        print ModuleName, "wlan0 up"
        os.system("service dnsmasq start")
        print ModuleName, "dnsmasq started"
        os.system("service hostapd start")
        print ModuleName, "hostapd started"
        # Because wlan0 loses its ip address when hostapd is started
        os.system("ifconfig wlan0 10.0.0.1")
    elif switchTo == "client":
        os.system("ifdown wlan0")
        print ModuleName, "wlan0 down"
        os.system("service dnsmasq stop")
        print ModuleName, "dnsmasq stopped"
        os.system("service hostapd stop")
        print ModuleName, "hostapd stopped"
        os.system("cp interfaces.client /etc/network/interfaces")
        os.system("ifup wlan0")
        print ModuleName, "wlan0 up"
    else:
        print ModuleName, "Must switch to either client or server"
        sys.exit()

