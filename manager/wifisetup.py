#!/usr/bin/env python
# wifisetup.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "wifisetup"
PING_TIMEOUT = 10

import sys
import time
import os
from subprocess import call
import pexpect
from cbconfig import *
import logging


def checkInterface():
    """ Determines if we have an ip address on eth0, wlan0, both or neither. """
    logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
    logging.debug("%s checkInterface", ModuleName)
    connectMode = "none"
    cmd = 'ifconfig eth0'
    p = pexpect.spawn(cmd)
    index = p.expect(['inet addr', pexpect.TIMEOUT, pexpect.EOF], timeout=3)
    if index == 1:
        logging.warning("%s pexpect timeout on ifconfig eth0", ModuleName)
    elif index == 2:
        logging.debug("%s Not connected by eth0", ModuleName)
    else:
        connectMode = "eth0"
    cmd = 'ifconfig wlan0'
    p = pexpect.spawn(cmd)
    index = p.expect(['Bcast', pexpect.TIMEOUT, pexpect.EOF], timeout=3)
    if index == 1:
        logging.warning("%s pexpect timeout on ifconfig wlan0", ModuleName)
    elif index == 2:
        logging.debug("%s Not connected by wlan0", ModuleName)
    else:
        raw = p.before.split()
        logging.debug("%s raw from pexpect: %s", ModuleName, raw)
        if raw[6] == "addr:10.0.0.1":
            logging.info("%s WiFi had server address", ModuleName)
        else:
            if connectMode == "eth0":
                connectMode = "both"
            else:
                connectMode = "wlan0"
    if CB_WLAN_TEST:
        if connectMode == "eth0":
            # Allows testing of WiFi while connected the eth0
            logging.debug("%s In CB_WLAN_TEST mode", ModuleName)
            return "none"
        else:
            return connectMode
    else:
        return connectMode

def clientConnected():
    attempt = 0
    cmd = 'ping continuumbridge.com'
    while attempt < 2: 
        try:
            p = pexpect.spawn(cmd)
        except:
            logging.error("%s Cannot spawn ping", ModuleName)
            attempt += 1
        index = p.expect(['time', pexpect.TIMEOUT, pexpect.EOF], timeout=PING_TIMEOUT)
        if index == 1 or index == 2:
            logging.warning("%s %s did not succeed", ModuleName, cmd)
            p.kill(9)
            cmd = 'ping bbc.co.uk'
            attempt += 1
        else:
            p.kill(9)
            return True
    # If we don't return before getting here, we've failed
    return False
 
def getCredentials():
    exe = CB_BRIDGE_ROOT + "/manager/wificonfig.py"
    logging.debug("%s getCredentials exe = %s", ModuleName, exe)
    try:
        p = pexpect.spawn(exe)
    except:
        logging.error("%s Cannot run wificonfig.py", ModuleName)
    index = p.expect(['Credentials.*', pexpect.TIMEOUT, pexpect.EOF], timeout=CB_GET_SSID_TIMEOUT)
    if index == 1:
        logging.warning("%s SSID and WPA key not supplied before timeout", ModuleName)
        return False, "none", "none"
    else:
        raw = p.after.split()
        logging.debug("%s Credentials = %s", ModuleName, raw)
        ssid = raw[2]
        wpa_key = raw[3]
        logging.info("%s SSID = %s, WPA = %s", ModuleName, ssid, wpa_key)
        return True, ssid, wpa_key
    p.kill(9)

def getConnected():
    """ If the Bridge is not connected assume that we are going to connect
        using WiFi. Try to connect using current settings. If we cannot,
        switch to server mode and ask user for SSDI and WPA key with a 
        2 minute timeout. If we have got credentials, use these and try
        again, otherwise return with failed status.
    """
    logging.info("%s getConnected. Switching to server mode", ModuleName)
    switchwlan0("server")
    gotCreds, ssid, wpa_key = getCredentials()
    if gotCreds:
        try:
            call(["rm", "/etc/wpa_supplicant/wpa_supplicant.conf"])
        except:
            logging.wwarning("%s Cannot rm wpa_supplicant.conf", ModuleName)
        wpa_proto_file = CB_BRIDGE_ROOT + "/bridgeconfig/wpa_supplicant.conf.proto"
        wpa_config_file = CB_CONFIG_DIR + "/wpa_supplicant.conf"
        i = open(wpa_proto_file, 'r')
        o = open(wpa_config_file, 'a')  #append new SSID to file
        for line in i:
            line = line.replace("XXXX", ssid)
            line = line.replace("YYYY", wpa_key)
            o.write(line) 
        i.close()
        o.close()
    else:
        logging.info("%s Did not get WiFi SSID and WPA from a human", ModuleName)
    switchwlan0("client")
    c = checkInterface()
    if c != "none":
        logging.info("%s Client connected by %s", ModuleName, c)
        return True
    else:
        return False

def connectClient():
    connected = False
    try:
        p = pexpect.spawn("ifup wlan0")
    except:
        logging.warning("%s Cannot spawn ifup wlan0", ModuleName)
    else:
        index = p.expect(['bound',  pexpect.TIMEOUT, pexpect.EOF], timeout=60)
        if index == 0:
            logging.info("%s wlan0 connected in client mode", ModuleName)
            connected = True
        elif index == 2:
            for t in p.before.split():
                if t == "already":
                    logging.info("%s wlan0 already connected. No need to connect.", ModuleName)
                    connected = True
                    break
        else:
            logging.warning("%s DHCP failed", ModuleName)
            p.kill(9)
    return connected

def switchwlan0(switchTo):
    logging.info("%s Switching to %s", ModuleName, switchTo)
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
