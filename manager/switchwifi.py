#!/usr/bin/env python
# switchwifi.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#

""" Switches wlan0 between being an access point and a client """

ModuleName = "Switch WiFi          "

import sys
import time
import os
from subprocess import call
import pexpect

class SwitchWiFi:

    def __init__(self):
        self.bridgeRoot = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
        print ModuleName, "CB_BRIDGE_ROOT = ", self.bridgeRoot

    def switch(self, switchTo):
        print ModuleName, "Switching to ", switchTo
   
        if switchTo == "server":
            call(["ifdown", "wlan0"])
            print ModuleName, "wlan0 down"
            call(["killall", "wpa_supplicant"])
            print ModuleName, "wpa_supplicant process killed"
            interfacesFile = self.bridgeRoot + "/bridgeconfig/interfaces.server"
            call(["cp", interfacesFile, "/etc/network/interfaces"])
            call(["ifup", "wlan0"])
            print ModuleName, "wlan0 up"
            dnsmasqFile = self.bridgeRoot + "/bridgeconfig/dnsmasq.conf"
            call(["cp", dnsmasqFile, "/etc/dnsmasq.conf"])
            call(["service", "dnsmasq", "start"])
            print ModuleName, "dnsmasq started"
            hostapdFile = self.bridgeRoot + "/bridgeconfig/hostapd"
            call(["cp", hostapdFile, "/etc/default/hostapd"])
            call(["service",  "hostapd", "start"])
            print ModuleName, "hostapd started"
            # Because wlan0 loses its ip address when hostapd is started
            call(["ifconfig", "wlan0", "10.0.0.1"])
        elif switchTo == "client":
            call(["ifdown", "wlan0"])
            print ModuleName, "wlan0 down"
            call(["service", "dnsmasq", "stop"])
            print ModuleName, "dnsmasq stopped"
            call(["service", "hostapd", " stop"])
            print ModuleName, "hostapd stopped"
            try:
                call(["rm", "/etc/dnsmasq.conf"])
            except:
                print ModuleName, "Unable to remove /etc/dnsmasq.conf. Already in client mode?"
            try:
                call(["rm", "/etc/default/hostapd"])
            except:
                print ModuleName, "Unable to remove /etc/default.hostapd. Already in client mode?"
            interfacesFile = self.bridgeRoot + "/bridgeconfig/interfaces.client"
            call(["cp", interfacesFile, "/etc/network/interfaces"])
            wpa_config_file = self.bridgeRoot + "/bridgeconfig/wpa_supplicant.conf"
            call(["cp", wpa_config_file, "/etc/wpa_supplicant/wpa_supplicant.conf"])
            call(["ifup", "wlan0"])
            print ModuleName, "wlan0 up"
        else:
            print ModuleName, "Must switch to either client or server"
            sys.exit()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print "Usage: switchwifi [client|server]"
        exit(1)
    s = SwitchWiFi()
    s.switch(sys.argv[1])
