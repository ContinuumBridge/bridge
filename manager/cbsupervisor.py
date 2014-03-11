#!/usr/bin/env python
# cbsupervisor.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Supervisor"

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
from cbconfig import *

class Supervisor:
    def __init__(self):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        logging.info("%s *************************************", ModuleName)
        logging.info("%s Restart", ModuleName)
        logging.info("%s *************************************", ModuleName)
        self.watchDogInterval = 30 # Number of secs between bridge manager checks
        self.connectionCheckInterval = 60 # Check internet connection this often
        self.reconnectCount = 0  
        self.maxReconnectCount = 10
        self.starting = True
        self.wiFiSetup = WiFiSetup()
        self.startManager(False)

    def startManager(self, restart):
        # Open a socket for communicating with the bridge manager
        s = CB_SOCKET_DIR + "skt-super-mgr"
        # Try to remove socket in case of prior crash & no clean-up
        try:
            os.remove(s)
        except:
            logging.debug("%s Socket was not present %s", ModuleName, s)
        if not restart:
            self.cbManagerFactory = CbServerFactory(self.processManager)
        self.mgrPort = reactor.listenUNIX(s, self.cbManagerFactory, backlog=4)

        # Start the manager in a subprocess
        exe = CB_BRIDGE_ROOT + "/manager/cbmanager.py"
        try:
            self.managerProc = Popen([exe])
            logging.info("%s Starting bridge manager", ModuleName)
            self.starting = False
            reactor.callLater(2*self.watchDogInterval, self.checkManager, time.time())
        except:
            logging.error("%s Bridge manager failed to start: %s", ModuleName, exe)
        
        if not restart:
            # Only check connections when not in simulation mode
            try:
                reactor.callLater(0.5, self.checkConnection)
            except:
                logging.error("%s iUnable to call checkConnection", ModuleName)
            reactor.run()

    def cbSendManagerMsg(self, msg):
        logging.debug("%s Sending msg to manager: %s", ModuleName, msg)
        self.cbManagerFactory.sendMsg(msg)

    def processManager(self, msg):
        logging.debug("%s processManager received: %s", ModuleName, msg)
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
                logging.warning("%s Manager appears to be dead. Trying to restart nicely", ModuleName)
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
        logging.info("%s Checked LAN connection %s", ModuleName, connected)
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
            logging.info("%s Cannot tell manager to stop, just rebooting", ModuleName)
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
        if CB_SIM_LEVEL == 0:
            try:
                call(["reboot"])
            except:
                logging.info("%s Unable to reboot, probably because bridge not run as root", ModuleName)
        else:
            logging.info("%s Would have rebooted if not in sum mode", ModuleName)

if __name__ == '__main__':
    s = Supervisor()
