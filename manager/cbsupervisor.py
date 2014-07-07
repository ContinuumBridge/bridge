#!/usr/bin/env python
# cbsupervisor.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Supervisor"

TIME_TO_IFUP = 15              # Time to wait before checking if we have an Internet connection (secs)
WATCHDOG_INTERVAL = 30         # Time between manager checks (secs)
CONNECT_CHECK_INTERVAL = 60    # How often to check LAN connection
MAX_NO_SERVER_COUNT = 10       # Used when making decisions about rebooting
MIN_TIME_BETWEEN_REBOOTS = 600 # Stops constant rebooting (secs)
REBOOT_WAIT = 10               # Time to allow bridge to stop before rebooting
RESTART_INTERVAL = 8           # Time between telling manager to stop and starting it again
MAX_INTERFACE_CHECKS = 10      # No times to check interface before rebooting
EXIT_WAIT = 2                  # On SIGINT, time to wait before exit after manager signalled to stop

import sys
import signal
import time
import os
import wifisetup
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
        logging.info("%s ************************************************************", ModuleName)
        logging.info("%s Restart", ModuleName)
        logging.info("%s ************************************************************", ModuleName)
        logging.info("%s BEWARE. LOG TIMES MAY BE WRONG BEFORE TIME UPDATED VIA NTP", ModuleName)
        logging.info("%s CB_LOGGING_LEVEL =  %s", ModuleName, CB_LOGGING_LEVEL)
        try:
            versionFile =  CB_BRIDGE_ROOT + "/manager/" + "cb_version"
            with open(versionFile, 'r') as f:
                v = f.read()
            if v.endswith('\n'):
                v = v[:-1]
        except:
            v = "Unknown"
        logging.info("%s Bridge version =  %s", ModuleName, v)
        logging.info("%s ************************************************************", ModuleName)
        self.starting = True    # Don't check manager watchdog when manager not running
        self.connecting = True  # Ignore conduit not connected messages if trying to connect
        self.timeStamp = time.time()
        self.beginningOfTime = time.time() # Used when making decisions about rebooting
        self.noServerCount = 0             # Used when making decisions about rebooting
        self.interfaceChecks = 0
        self.managerStopped = False
        signal.signal(signal.SIGINT, self.signalHandler)  # For catching SIGINT
        signal.signal(signal.SIGTERM, self.signalHandler)  # For catching SIGTERM
        try:
            reactor.callLater(TIME_TO_IFUP, self.checkInterface)
        except:
            logging.error("%s iUnable to call checkInterface", ModuleName)

        reactor.callLater(1, self.startManager, False)
        reactor.run()

    def startManager(self, restart):
        # Remove file that signifies that manager has exited 
        if os.path.exists(CB_MANAGER_EXIT):
            os.remove(CB_MANAGER_EXIT)
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
        
    def cbSendManagerMsg(self, msg):
        #logging.debug("%s Sending msg to manager: %s", ModuleName, msg)
        self.cbManagerFactory.sendMsg(msg)

    def processManager(self, msg):
        #logging.debug("%s processManager received message: %s", ModuleName, msg)
        # Regardless of message content, timeStamp is the time when we last heard from the manager
        self.timeStamp = time.time()
        if msg["msg"] == "restart":
            logging.info("%s processManager restarting", ModuleName)
            self.cbSendManagerMsg({"msg": "stopall"})
            self.starting = True
            reactor.callLater(RESTART_INTERVAL, self.checkManagerStopped, 0)
        elif msg["msg"] == "reboot":
            logging.info("%s Reboot message received from manager", ModuleName)
            self.starting = True
            self.doReboot()
        elif msg["msg"] == "stopped":
            self.managerStopped = True
        elif msg["msg"] == "status":
            if msg["status"] == "disconnected":
                logging.info("%s status = %s, connecting = %s", ModuleName, msg["status"], self.connecting)
                if not self.connecting:
                    if wifisetup.clientConnected():
                        logging.info("%s Connected to Internet but not to server", ModuleName)
                        self.noServerCount += 1
                    if time.time() - self.beginningOfTime > MIN_TIME_BETWEEN_REBOOTS or \
                    self.noServerCount > MAX_NO_SERVER_COUNT:
                        self.doReboot()
            else:
                self.noServerCount = 0

    def checkManagerStopped(self, count):
        if os.path.exists(CB_MANAGER_EXIT):
            logging.debug("%s checkManagerStopped. Manager stopped", ModuleName)
            os.remove(CB_MANAGER_EXIT)
            self.startManager(True)
        elif count < 3:
            reactor.callLater(RESTART_INTERVAL, self.checkManagerStopped, count + 1)
            logging.info("%s checkManagerStopped. Manager not stopped yet, count: %s", ModuleName, count)
        else:
            logging.warning("%s checkManagerStopped. Manager not stopped after count %s, rebooting", ModuleName, count)
            self.reboot()

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
                    logging.warning("%s Cannot send message to manager. Rebooting", ModuleName)
                    self.killBridge()

    def recheckManager(self, startTime):
        logging.debug("%s recheckManager", ModuleName)
        # Whatever happened, stop listening on manager port.
        self.mgrPort.stopListening()
        if self.timeStamp > startTime - 1:
            # Manager responded to request to stop. Restart it.
            logging.info("%s Manager stopped sucessfully. Restarting ...", ModuleName)
            reactor.callLater(1, self.startManager,True) 
        else:
            # Manager is well and truely dead.
            logging.warning("%s Manager is well and truly dead. Rebooting", ModuleName)
            self.killBridge()

    def killBridge(self):
        # For now, just do a reboot rather than anything more elegant
        self.reboot()

    def checkInterface(self):
        # Defer to thread - it could take several seconds
        logging.debug("%s checkInterface called", ModuleName)
        d1 = threads.deferToThread(wifisetup.checkInterface)
        d1.addCallback(self.interfaceChecked)

    def interfaceChecked(self, mode):
        logging.info("%s Connected by %s", ModuleName, mode)
        if mode == "none":
            d = threads.deferToThread(wifisetup.getConnected)
            d.addCallback(self.checkConnected)
        else:
            self.connecting = False

    def checkConnected(self, connected):
        if connected:
            self.connecting = False
        else:
            if self.interfaceChecks > MAX_INTERFACE_CHECKS:
                logging.info("%s Unable to connect to a network. Rebooting ...", ModuleName)
                self.doReboot()
            else:
                self.interfaceChecks += 1
                logging.debug("%s checkConnected. interfaceChecks = %s", ModuleName, self.interfaceChecks)
                self.checkInterface()

    def doReboot(self):
        """ Give bridge manager a chance to tidy up nicely before rebooting. """
        try:
            self.cbSendManagerMsg({"msg": "stopall"})
        except:
            logging.info("%s Cannot tell manager to stop, just rebooting", ModuleName)
        # Tidy up
        #self.mgrPort.stopListening()
        reactor.callLater(REBOOT_WAIT, self.reboot)

    def reboot(self):
        logging.info("%s Rebooting", ModuleName)
        try:
            reactor.stop()
        except:
            logging.info("%s Unable to stop reactor, just rebooting", ModuleName)
        if CB_SIM_LEVEL == '0':
            try:
                logging.info("%s Rebooting now. Goodbye ...", ModuleName)
                call(["reboot"])
            except:
                logging.info("%s Unable to reboot, probably because bridge not run as root", ModuleName)
        else:
            logging.info("%s Would have rebooted if not in sim mode", ModuleName)

    def signalHandler(self, signal, frame):
        logging.debug("%s signalHandler received signal", ModuleName)
        self.cbSendManagerMsg({"msg": "stopall"})
        reactor.callLater(EXIT_WAIT, self.exitSupervisor)

    def exitSupervisor(self):
        logging.info("%s exiting", ModuleName)
        reactor.stop()
        sys.exit
        
if __name__ == '__main__':
    s = Supervisor()
