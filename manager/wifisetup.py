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

    def __init__(self, bridgeRoot):
        print ModuleName
        self.bridgeRoot = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
        print ModuleName, "CB_BRIDGE_ROOT = ", self.bridgeRoot

    def checkClientConnected(self):
        try:
            cmd = 'ping -b 255.255.255.255'
            p = pexpect.spawn(cmd)
        except:
            print ModuleName, "Can't spawn ping to broadcast address"
            self.connected = False
        index = p.expect(['time', pexpect.TIMEOUT], timeout=10)
        if index == 1:
            print ModuleName, "Client connection timed out. Changing to server"
            p.kill(9)
            return "timeout"
        else:
            return "connected"
 
    def getCredentials(self):
        exe = self.bridgeRoot + "/manager/wificonfig.py"
        print ModuleName, "getCredentials exe = ", exe
        try:
            p = pexpect.spawn(exe)
        except:
            print ModuleName, "Can't run wificonfig"
            self.connected = False
        index = p.expect(['Credentials.*', pexpect.TIMEOUT], timeout=120)
        if index == 1:
            print ModuleName, "SSID and WPA key not supplied before timeout"
            p.kill(9)
            return False
        else:
            raw = p.after.split()
            print ModuleName, "Credentials = ", raw
            self.ssid = raw[2]
            self.wpa_key = raw[3]
            print ModuleName, "ssid = ", self.ssid, "wpa = ", self.wpa_key
            return True

    def getConnected(self):
        s = SwitchWiFi()
        # Ensure we are in client mode
        s.switch("client")
        clientConnected = self.checkClientConnected()
        clientConnected = False
        if clientConnected:
            print ModuleName, "Client connected: ", clientConnected
            sys.exit()
        else:
            print ModuleName, "Can't connect. Switching to server mode"
            s.switch("server")
        ok = self.getCredentials()
        if ok:
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
        else:
            print ModuleName, "Not OK"

if __name__ == '__main__':
    wiFiSetup = WiFiSetup(sys.argv)
    wiFiSetup.getConnected()
