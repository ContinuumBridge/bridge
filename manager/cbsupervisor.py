#!/usr/bin/env python
# cbsupervisor.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Supervisor"

TIME_TO_IFUP = 10 # Time to wait before checking if we have an Internet connection (secs)
WATCHDOG_INTERVAL = 30  # Time between manager checks (secs)
CONNECT_CHECK_INTERVAL = 60

import sys
import time
import os
from wifisetup import WiFiSetup
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
        logging.info("%s CB_LOGGIN_LEVEL =  %s", ModuleName, CB_LOGGING_LEVEL)
        self.starting = True    # Don't check manager watchdog when manager not running
        self.connecting = True  # Ignore conduit not connected messages if trying to connect
        self.timeStamp = time.time()
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
        #if not restart:
        self.cbManagerFactory = CbServerFactory(self.processManager)
        self.mgrPort = reactor.listenUNIX(s, self.cbManagerFactory, backlog=4)

        # Start the manager in a subprocess
        exe = CB_BRIDGE_ROOT + "/manager/cbmanager.py"
        try:
            self.managerProc = Popen([exe])
            logging.info("%s Starting bridge manager", ModuleName)
            self.starting = False
            reactor.callLater(2*WATCHDOG_INTERVAL, self.checkManager, time.time())
        except:
            logging.error("%s Bridge manager failed to start: %s", ModuleName, exe)
        
        try:
            reactor.callLater(TIME_TO_IFUP, self.checkInterface)
        except:
            logging.error("%s iUnable to call checkInterface", ModuleName)
        reactor.run()

    def cbSendManagerMsg(self, msg):
        logging.debug("%s Sending msg to manager: %s", ModuleName, msg)
        self.cbManagerFactory.sendMsg(msg)

    def processManager(self, msg):
        logging.debug("%s processManager received: %s", ModuleName, msg)
        # Regardless of message content, timeStamp is the time when we last heard from the manager
        self.timeStamp = time.time()
        if msg["msg"] == "restart":
            resp = {"msg": "stopall"
                   }
            self.cbSendManagerMsg(resp)
            self.starting = True
            reactor.callLater(WATCHDOG_INTERVAL, self.startManager, True)
        elif msg["msg"] == "reboot":
            self.starting = True
            self.doReboot()
        elif msg["msg"] == "status":
            logging.debug("%s status = %s", ModuleName, msg["status"])
            if msg["status"] == "disconnected":
                logging.debug("%s status = %s, connecting = %s", ModuleName, msg["status"], self.connecting)
                if not self.connecting:
                    self.doRebbot()

    def checkManager(self, startTime):
        if not self.starting:
            # -1 is allowance for times not being sync'd (eg: separate devices)
            if self.timeStamp > startTime - 1:
                reactor.callLater(WATCHDOG_INTERVAL, self.checkManager, time.time())
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
                    reactor.callLater(WATCHDOG_INTERVAL, self.recheckManager, time.time())
                except:
                    reactor.callLater(WATCHDOG_INTERVAL, self.startManager,True) 

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

    def checkInterface(self):
        # Defer to thread - it could take several seconds
        logging.debug("%s checkInterface called", ModuleName)
        self.wiFiSetup.checkInterface()
        d1 = threads.deferToThread(self.wiFiSetup.checkInterface)
        d1.addCallback(self.interfaceChecked)

    def interfaceChecked(self, mode):
        logging.info("%s Connected by %s", ModuleName, mode)
        if mode == "none":
            d = threads.deferToThread(self.wiFiSetup.getConnected)
            d.addCallback(self.checkReconnected)
        else:
            self.connecting = False

    def checkReconnected(self, connected):
        """ Detected we were not connected. Tried to reconnect. If not connected, reboot. """
        if connected:
            self.connecting = False
        else:
            self.doReboot()

    def doReboot(self):
        """ Give bridge manager a chance to tidy up nicely before rebooting. """
        try:
            msg = {"msg": "stopall"
                  }
            self.cbSendManagerMsg(msg)
        except:
            logging.info("%s Cannot tell manager to stop, just rebooting", ModuleName)
        # Tidy up
        #self.mgrPort.stopListening()
        reactor.callLater(WATCHDOG_INTERVAL, self.reboot)

    def reboot(self):
        try:
            reactor.stop()
        except:
            logging.info("%s Unable to stop reactor, just rebooting", ModuleName)
        if CB_SIM_LEVEL == '0':
            try:
                call(["reboot"])
            except:
                logging.info("%s Unable to reboot, probably because bridge not run as root", ModuleName)
        else:
            logging.info("%s Would have rebooted if not in sim mode", ModuleName)

if __name__ == '__main__':
    s = Supervisor()
