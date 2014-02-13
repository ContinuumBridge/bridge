#!/usr/bin/env python
# wifisetup.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "WiFiSetup           "

import sys
import time
import os
import json
from pprint import pprint
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
#from cbcommslib import CbClientProtocol
#from cbcommslib import CbClientFactory
#from cbcommslib import CbServerProtocol
#from cbcommslib import CbServerFactory

class WiFiSetup():

    def __init__(self):
        print ModuleName
        self.bridgeRoot = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
        print ModuleName, "CB_BRIDGE_ROOT = ", self.bridgeRoot

    def clientConnected(self):
        try:
            cmd = 'ping -b 255.255.255.255'
            # This is ContinuumBridge portal ip address
            cmd = 'ping 54.194.28.63'
            p = pexpect.spawn(cmd)
        except:
            print ModuleName, "Can't spawn ping"
            self.connected = False
        index = p.expect(['time', pexpect.TIMEOUT], timeout=10)
        if index == 1:
            print ModuleName, "Client connection timed out. Changing to server"
            p.kill(9)
            return False
        else:
            p.kill(9)
            return True
 
    def getCredentials(self):
        exe = self.bridgeRoot + "/manager/wificonfig.py"
        print ModuleName, "getCredentials exe = ", exe
        try:
            p = pexpect.spawn(exe)
        except:
            print ModuleName, "Can't run wificonfig"
            self.connected = False
        index = p.expect(['Credentials.*', pexpect.TIMEOUT], timeout=120)
        p.kill(9)
        if index == 1:
            print ModuleName, "SSID and WPA key not supplied before timeout"
            return False
        else:
            raw = p.after.split()
            print ModuleName, "Credentials = ", raw
            self.ssid = raw[2]
            self.wpa_key = raw[3]
            print ModuleName, "ssid = ", self.ssid, "wpa = ", self.wpa_key
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
        s.switch("client")
        if clientConnected():
            return True
        else:
            print ModuleName, "Can't connect. Switching to server mode"
            s.switch("server")
            if self.getCredentials():
                try:
                    call(["rm", "/etc/wpa_supplicant/wpa_supplicant.conf"])
                except:
                    pass
                wpa_proto_file = self.bridgeRoot + "/bridgeconfig/wpa_supplicant.conf.proto"
                wpa_config_file = self.bridgeRoot + "/bridgeconfig/wpa_supplicant.conf"
                i = open(wpa_proto_file, 'r')
                o = open(wpa_config_file, 'w')
                for line in i:
                    line = line.replace("XXXX", self.ssid)
                    line = line.replace("YYYY", self.wpa_key)
                    o.write(line) 
                i.close()
                o.close()
                s.switch("client")
                if clientConnected():
                    print ModuleName, "Client connected"
                    return True
                else:
                    return False
            else:
                print ModuleName, "Did not get WiFi SSID & WPA from a human."
                return False
    
if __name__ == '__main__':
    wiFiSetup = WiFiSetup()
    wiFiSetup.getConnected()
