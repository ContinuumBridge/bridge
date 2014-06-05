#!/usr/bin/env python
# switchwifi.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#

""" Switches wlan0 between being an access point and a client """

ModuleName = "Switch WiFi"

import sys
import time
import os
from subprocess import call
import pexpect
import logging
from cbconfig import *


def connectClient():
    connected = False
    try:
        p = pexpect.spawn("ifup wlan0")
    except:
        logging.warning("%s Cannot spawn ifup wlan0", ModuleName)
    else:
        index = p.expect(['bound',  pexpect.TIMEOUT, pexpect.EOF], timeout=60)
        if index == 0:
            logging.info("%s Connected in client mode", ModuleName)
            connected = True
        elif index == 2:
            for t in p.before.split():
                if t == "already":
                    connected = True
                    break
        else:
            logging.warning("%s DHCP failed", ModuleName)
            p.kill(9)
    return connected

def switch(switchTo):
    print ModuleName, "Switching to ", switchTo
   
    if switchTo == "server":
        call(["ifdown", "wlan0"])
        logging.debug("%s wlan0 down", ModuleName)
        call(["killall", "wpa_supplicant"])
        logging.debug("%s wpa_supplicant process killed", ModuleName)
        interfacesFile = CB_BRIDGE_ROOT + "/bridgeconfig/interfaces.server"
        call(["cp", interfacesFile, "/etc/network/interfaces"])
        call(["ifup", "wlan0"])
        logging.debug("%s wlan0 up", ModuleName)

        # dnsmasq - dhcp server
        dnsmasqFile = CB_BRIDGE_ROOT + "/bridgeconfig/dnsmasq.conf"
        call(["cp", dnsmasqFile, "/etc/dnsmasq.conf"])
        call(["service", "dnsmasq", "start"])
        logging.info("%s dnsmasq started", ModuleName)
        
        # hostapd configuration and start
        hostapdFile = CB_BRIDGE_ROOT + "/bridgeconfig/hostapd"
        call(["cp", hostapdFile, "/etc/default/hostapd"])
        # Just in case it's not there:
        hostapdFile = CB_BRIDGE_ROOT + "/bridgeconfig/hostapd.conf"
        call(["cp", hostapdFile, "/etc/hostapd/hostapd.conf"])
        call(["service",  "hostapd", "start"])
        logging.info("%s hostapd started", ModuleName)
        # Because wlan0 loses its ip address when hostapd is started
        call(["ifconfig", "wlan0", "10.0.0.1"])
        logging.info("%s Wifi in server mode", ModuleName)
    elif switchTo == "client":
        call(["ifdown", "wlan0"])
        logging.debug("%s wlan0 down", ModuleName)
        call(["service", "dnsmasq", "stop"])
        logging.info("%s dnsmasq stopped", ModuleName)
        call(["service", "hostapd", " stop"])
        logging.info("%s hostapd stopped", ModuleName)
        try:
            call(["rm", "/etc/dnsmasq.conf"])
        except:
            logging.info("%s dUnable to remove /etc/dnsmasq.conf. Already in client mode?", ModuleName)
        try:
            call(["rm", "/etc/default/hostapd"])
        except:
            logging.info("%s Unable to remove /etc/default.hostapd. Already in client mode?", ModuleName)
        interfacesFile = CB_BRIDGE_ROOT + "/bridgeconfig/interfaces.client"
        call(["cp", interfacesFile, "/etc/network/interfaces"])
        wpa_config_file = CB_CONFIG_DIR + "/wpa_supplicant.conf"
        call(["cp", wpa_config_file, "/etc/wpa_supplicant/wpa_supplicant.conf"])
        time.sleep(1)
        connectClient()
        logging.info("%s Wifi in client mode", ModuleName)
    else:
        logging.debug("%s switch. Must switch to either client or server", ModuleName)
        print ModuleName, "Must switch to either client or server"
