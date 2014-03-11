#!/usr/bin/env python
# wifisetup.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "WiFiSetup"

import sys
import time
import os
import json
from subprocess import call
import pexpect
from switchwifi import SwitchWiFi
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from twisted.internet import threads
from twisted.internet import defer
from twisted.internet import reactor
from twisted.application.internet import TCPServer
from twisted.application.service import Application
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet.task import deferLater
from twisted.web.server import NOT_DONE_YET
from cbconfig import *
import logging

class WiFiSetup():

    def __init__(self):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        logging.info("%s Hello", ModuleName)

    def clientConnected(self):
        try:
            # This is ContinuumBridge portal ip address
            cmd = 'ping continuumbridge.com'
            p = pexpect.spawn(cmd)
        except:
            logging.error("%s Cannot spawn ping", ModuleName)
            self.connected = False
        index = p.expect(['time', pexpect.TIMEOUT], timeout=10)
        if index == 1:
            logging.warning("%s CClient connection timed out. Changing to server", ModuleName)
            p.kill(9)
            return False
        else:
            p.kill(9)
            return True
 
    def getCredentials(self):
        exe = CB_BRIDGE_ROOT + "/manager/wificonfig.py"
        logging.info("%s getCredentials exe = ", ModuleName, exe)
        try:
            p = pexpect.spawn(exe)
        except:
            logging.error("%s Cannot run wificonfig.py", ModuleName)
            self.connected = False
        index = p.expect(['Credentials.*', pexpect.TIMEOUT], timeout=300)
        p.kill(9)
        if index == 1:
            logging.warning("%s SSID and WPA key not supplied before timeout", ModuleName)
            return False
        else:
            raw = p.after.split()
            logging.debug("%s Credentials = %s", ModuleName, raw)
            self.ssid = raw[2]
            self.wpa_key = raw[3]
            logging.info("%s SSID = %s, WPA = %s", ModuleName, self.ssid, self.wpa_key)
            return True

    def getConnected(self):
        """ If the Bridge is not connected assume that we are going to connect
            using WiFi. Try to connect using current settings. If we cannot,
            switch to server mode and ask user for SSDI and WPA key with a 
            2 minute timeout. If we have got credentials, use these and try
            again, otherwise return with failed status.
        """
        s = SwitchWiFi()
        # Ensure we are in client mode
        #s.switch("client")
        #if self.clientConnected():
        #    return True
        #else:
        if True:
            logging.info("%s Cannot connect. Switching to server mode", ModuleName)
            s.switch("server")
            if self.getCredentials():
                try:
                    call(["rm", "/etc/wpa_supplicant/wpa_supplicant.conf"])
                except:
                    pass
                wpa_proto_file = self.bridgeRoot + "/bridgeconfig/wpa_supplicant.conf.proto"
                wpa_config_file = self.bridgeRoot + "/thisbridge/wpa_supplicant.conf"
                i = open(wpa_proto_file, 'r')
                o = open(wpa_config_file, 'w')
                for line in i:
                    line = line.replace("XXXX", self.ssid)
                    line = line.replace("YYYY", self.wpa_key)
                    o.write(line) 
                i.close()
                o.close()
                s.switch("client")
                if self.clientConnected():
                    logging.info("%s Client connected", ModuleName)
                    return True
                else:
                    return False
            else:
                logging.info("%s Did not get WiFi SSID and WPA from a human", ModuleName)
                return False
    
if __name__ == '__main__':
    wiFiSetup = WiFiSetup()
    wiFiSetup.getConnected()
