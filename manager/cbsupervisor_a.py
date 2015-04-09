#!/usr/bin/env python
# cbsupervisor.py
# Copyright (C) ContinuumBridge Limited, 2014-2015 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
"""
"""
ModuleName = "Supervisor"

import sys
import signal
import time
import os
import glob
import procname
from subprocess import call
from subprocess import Popen
from subprocess import check_output
from twisted.internet import threads
from twisted.internet import reactor, defer
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory
from cbconfig import *
sys.path.insert(0, CB_BRIDGE_ROOT + "/conman")
import conman

MANAGER_START_TIME = 3            # Time to allow for manager to start before starting to monitor it (secs)
TIME_TO_IFUP = 90                 # Time to wait before checking if we have an Internet connection (secs)
WATCHDOG_INTERVAL = 30            # Time between manager checks (secs)
REBOOT_WAIT = 10                  # Time to allow bridge to stop before rebooting
RESTART_INTERVAL = 10             # Time between telling manager to stop and starting it again
EXIT_WAIT = 2                     # On SIGINT, time to wait before exit after manager signalled to stop
SAFETY_INTERVAL = 300             # Delay before rebooting if manager failed to start
NTP_UPDATE_INTERVAL = 12*3600     # How often to run ntpd to sync time

class Supervisor:
    def __init__(self):
        procname.setprocname('cbsupervisor')
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(levelname)s: %(message)s')
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
        self.connected = False
        signal.signal(signal.SIGINT, self.signalHandler)  # For catching SIGINT
        signal.signal(signal.SIGTERM, self.signalHandler)  # For catching SIGTERM
        reactor.callLater(0.1, self.startConman)
        reactor.callInThread(self.iptables)
        reactor.callLater(1, self.startManager, False)
        reactor.run()

    def startConman(self):
        self.conman = conman.Conman()
        self.conman.start(logFile=CB_LOGFILE, logLevel=CB_LOGGING_LEVEL)

    def startManager(self, restart):
        self.starting = True
        self.manageNTP()
        # Try to remove all sockets, just in case
        for f in glob.glob(CB_SOCKET_DIR + "skt-*"):
            os.remove(f)
        for f in glob.glob(CB_SOCKET_DIR + "SKT-*"):
            os.remove(f)
        # Remove file that signifies that manager has exited 
        if os.path.exists(CB_MANAGER_EXIT):
            os.remove(CB_MANAGER_EXIT)
        # Open a socket for communicating with the bridge manager
        s = CB_SOCKET_DIR + "skt-super-mgr"
        self.cbManagerFactory = CbServerFactory(self.onManagerMessage)
        self.mgrPort = reactor.listenUNIX(s, self.cbManagerFactory, backlog=4)

        # Start the manager in a subprocess
        exe = CB_BRIDGE_ROOT + "/manager/cbmanager.py"
        try:
            self.managerProc = Popen([exe])
            logging.info("%s Starting bridge manager", ModuleName)
            # Give time for manager to start before setting self.starting
            reactor.callLater(MANAGER_START_TIME, self.setStartingOff)
            if not CB_DEV_BRIDGE:
                if not self.checkingManager:
                    reactor.callLater(3*WATCHDOG_INTERVAL, self.checkManager, time.time())
                    checkingManager = True
        except Exception as ex:
            logging.error("%s Bridge manager failed to start: %s", ModuleName, exe)
            logging.error("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            # Give developer a chance to do something before rebooting:
            reactor.callLater(SAFETY_INTERVAL, self.reboot)
        
    def cbSendManagerMsg(self, msg):
        #logging.debug("%s Sending msg to manager: %s", ModuleName, msg)
        self.cbManagerFactory.sendMsg(msg)

    def onManagerMessage(self, msg):
        #logging.debug("%s onManagerMessage received message: %s", ModuleName, msg)
        # Regardless of message content, timeStamp is the time when we last heard from the manager
        self.timeStamp = time.time()
        if msg["msg"] == "restart":
            logging.info("%s onManagerMessage restarting", ModuleName)
            self.cbSendManagerMsg({"msg": "stopall"})
            self.starting = True
            reactor.callLater(RESTART_INTERVAL, self.checkManagerStopped, 0)
        elif msg["msg"] == "restart_cbridge":
            logging.info("%s onManagerMessage restart_cbridge", ModuleName)
            self.starting = True
            reactor.callLater(0, self.restartCbridge)
        elif msg["msg"] == "reboot":
            logging.info("%s Reboot message received from manager", ModuleName)
            self.starting = True
            reactor.callFromThread(self.doReboot)
        elif msg["msg"] == "status":
            if msg["status"] == "disconnected":
                logging.info("%s onManagerMessage. status: %s, disconnected:  %s, self.connecting: %s", ModuleName, msg["status"], self.disconnected, self.connecting)

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

    def setStartingOff(self):
        self.starting = False

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
                except Exception as ex:
                    logging.warning("%s Cannot send message to manager. Rebooting", ModuleName)
                    logging.error("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
                    self.reboot()

    def recheckManager(self, startTime):
        logging.debug("%s recheckManager", ModuleName)
        # Whatever happened, stop listening on manager port.
        self.mgrPort.stopListening()
        # Manager responded to request to stop. Restart it.
        if self.timeStamp > startTime - 1 and os.path.exists(CB_MANAGER_EXIT):
            logging.info("%s recheckManager. Manager stopped sucessfully. Restarting ...", ModuleName)
            os.remove(CB_MANAGER_EXIT)
            self.startManager(True)
        else:
            # Manager is well and truely dead.
            logging.warning("%s Manager is well and truly dead. Rebooting", ModuleName)
            self.reboot()

    def iptables(self):
        try:
            # This is zwave.me
            ip_to_block = "46.20.244.72"
            s = check_output(["iptables", "-A", "INPUT", "-s", ip_to_block, "-j", "DROP"])
            s = check_output(["iptables", "-A", "OUTPUT", "-s", ip_to_block, "-j", "DROP"])
        except Exception as ex:
            logging.warning("%s iptables setup failed", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))

    def doReboot(self):
        """ Give bridge manager a chance to tidy up nicely before rebooting. """
        logging.info("%s doReboot", ModuleName)
        if CB_CELLULAR_BRIDGE:
            try:
                Popen(["/usr/bin/modem3g/sakis3g", "--sudo", "disconnect"])
            except Exception as ex:
                logging.warning("%s deReboot. sakis3g disconnect failed", ModuleName)
                logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        try:
            self.cbSendManagerMsg({"msg": "stopall"})
        except Exception as ex:
            logging.warning("%s Cannot tell manager to stop, just rebooting", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        # Tidy up
        #self.mgrPort.stopListening()
        reactor.callLater(REBOOT_WAIT, self.reboot)

    def manageNTP(self):
        if self.connected:
            logging.info("%s Calling ntpd to update time", ModuleName)
            reactor.callInThread(self.manageNTPThread)
            reactor.callLater(NTP_UPDATE_INTERVAL, self.manageNTP)
        else:
            reactor.callLater(10, self.manageNTP)

    def manageNTPThread(self):
        try:
            syncd = False
            while not syncd:
                s = check_output(["sudo", "/usr/sbin/ntpd", "-p", "/var/run/ntpd.pid", "-g", "-q"])
                logging.info("%s NTP time updated %s", ModuleName, str(s))
                if "time" in str(s):
                    syncd = True
                else:
                    time.sleep(10)
        except Exception as ex:
            logging.warning("%s Cannot run NTP", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        
    def reboot(self):
        logging.info("%s Rebooting", ModuleName)
        try:
            reactor.stop()
        except Exception as ex:
            logging.warning("%s Unable to stop reactor, just rebooting", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        if CB_SIM_LEVEL == '0':
            try:
                logging.info("%s Rebooting now. Goodbye ...", ModuleName)
                call(["reboot"])
            except Exception as ex:
                logging.info("%s Unable to reboot, probably because bridge not run as root", ModuleName)
                logging.info("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        else:
            logging.info("%s Would have rebooted if not in sim mode", ModuleName)

    def restartCbridge(self):
        try:
            logging.info("%s Restarting cbridge", ModuleName)
            call(["service", "cbridge", "restart"])
        except Exception as ex:
            logging.warning("%s Unable to restart cbridge", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))

    def signalHandler(self, signal, frame):
        logging.debug("%s signalHandler received signal", ModuleName)
        self.cbSendManagerMsg({"msg": "stopall"})
        reactor.callLater(EXIT_WAIT, self.exitSupervisor)

    def exitSupervisor(self):
        logging.info("%s exiting", ModuleName)
        reactor.stop()
        sys.exit
        
if __name__ == '__main__':
    Supervisor()
