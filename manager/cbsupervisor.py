#!/usr/bin/env python
# cbsupervisor.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Supervisor          "

import sys
import time
import os
from  wifisetup import WiFiSetup
from subprocess import call
from subprocess import Popen
from twisted.internet import threads
from twisted.internet import reactor, defer
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory

class Supervisor:

    def __init__(self):
        self.bridgeRoot = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
        print ModuleName, "CB_BRIDGE_ROOT = ", self.bridgeRoot
        self.sim = os.getenv('CB_SIM_LEVEL', '0')
        print ModuleName, "CB_SIM = ", self.sim
        self.watchDogInterval = 30 # Number of secs between bridge manager checks
        self.connectionCheckInterval = 60 # Check internet connection this often
        self.reconnectCount = 0  
        self.maxReconnectCount = 10
        self.starting = True
        self.wiFiSetup = WiFiSetup()
        self.startManager(False)

    def startManager(self, restart):
        # Open a socket for communicating with the bridge manager
        s = "skt-super-mgr"
        # Try to remove socket in case of prior crash & no clean-up
        try:
            os.remove(s)
        except:
            print ModuleName, "Socket was not present: ", s
        if not restart:
            self.cbManagerFactory = CbServerFactory(self.processManager)
        self.mgrPort = reactor.listenUNIX(s, self.cbManagerFactory, backlog=4)

        # Start the manager in a subprocess
        exe = self.bridgeRoot + "/manager/cbmanager.py"
        try:
            self.managerProc = Popen([exe])
            print ModuleName, "Started bridge manager"
            self.starting = False
            reactor.callLater(2*self.watchDogInterval, self.checkManager, time.time())
        except:
            print ModuleName, "Bridge manager failed to start:", exe
        
        if not restart:
            # Only check connections when not in simulation mode
            try:
                reactor.callLater(0.5, self.checkConnection)
            except:
                print ModuleName, "Unable to call checkConnection"
            reactor.run()

    def cbSendManagerMsg(self, msg):
        print ModuleName, "Sending msg to manager: ", msg
        self.cbManagerFactory.sendMsg(msg)

    def processManager(self, msg):
        print ModuleName, "processManager received: ", msg
        self.timeStamp = time.time()
        if msg["msg"] == "restart":
            msg = {"msg": "stopall"
                  }
            self.cbSendManagerMsg(msg)
            self.starting = True
            reactor.callLater(self.watchDogInterval, self.startManager, True)
        elif msg["msg"] == "reboot":
            self.starting = True
            self.doReboot()

    def checkManager(self, startTime):
        if not self.starting:
            # -1 is allowance for times not being sync'd (eg: separate devices)
            if self.timeStamp > startTime - 1:
                reactor.callLater(self.watchDogInterval, self.checkManager, time.time())
                msg = {"msg": "status",
                       "status": "ok"
                      }
                self.cbSendManagerMsg(msg)
            else:
                print ModuleName, "Manager appears to be dead. Trying to restart nicely"
                msg = {"msg": "stopall"
                      }
                try:
                    self.cbSendManagerMsg(msg)
                    reactor.callLater(self.watchDogInterval, self.recheckManager, time.time())
                except:
                    reactor.callLater(self.watchDogInterval, self.startManager,True) 

    def recheckManager(self, startTime):
        # Whatever happened, stop listening on manager port.
        self.mgrPort.stopListening()
        if self.timeStamp > startTime - 1:
            # Manager responded to request to stop. Restart it.
            reactor.callLater(1, self.startManager,True) 
        else:
            # Manager is well and truely dead.
            self.killBridge()

    def killBridge(self):
        # For now, just do a reboot rather than anything more elegant
        self.reboot()

    def checkConnection(self):
        self.d1 = threads.deferToThread(self.wiFiSetup.clientConnected)
        self.d1.addCallback(self.connectionChecked)

    def connectionChecked(self, connected):
        print ModuleName, "Checked LAN connection, ", connected
        if connected:
            reactor.callLater(self.connectionCheckInterval, self.checkConnection)
        else:
            self.d2 = threads.deferToThreat(self.wiFiSetup.getConnected)
            self.d2.addCallback(self.checkReconnected)

    def checkReconnected(self, connected):
        if connected:
            self.reconnectCount = 0
            reactor.callLater(self.connectionCheckInterval, self.checkConnection)
        else:
            if self.reconnectCount > self.maxReconnectCount:
                self.doReboot()
            else:
                self.reconnectCount += 1    
                d = threads.deferToThreat(self.wiFiSetup.getConnected)
                d.addCallback(self.checkReconnected)

    def doReboot(self):
        """ Give bridge manager a chance to tidy up nicely before rebooting. """
        try:
            msg = {"msg": "stopall"
                  }
            self.cbSendManagerMsg(msg)
        except:
            print ModuleName, "Can't tell manager to stop, just rebooting."
        # Tidy up
        try:
            self.d1.cancel
            self.d2.cancel
        except:
            # just being lazy and masking errors
            pass
        self.mgrPort.stopListening()
        reactor.callLater(self.watchDogInterval, self.reboot)

    def reboot(self):
        reactor.stop()
        s = "skt-super-mgr"
        if self.sim == 0:
            call(["reboot"])
        else:
            print ModuleName, "Would have rebooted if not in sim mode."

if __name__ == '__main__':
    s = Supervisor()
