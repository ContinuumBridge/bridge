#!/usr/bin/env python
# cbsupervisor.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
"""
Revised behaviour:
If manager not connected, start the clock.
After CHECK_INTERFACE_DELAY and then every CHECK_INTERFACE_DELAY, restart interface.
If no connection after MIN_TIME_BETWEEN_REBOOTS, reboot.
If manager not talking, kill and restart.
"""
ModuleName = "Supervisor"

MANAGER_START_TIME = 3            # Time to allow for manager to start before starting to monitor it (secs)
TIME_TO_IFUP = 90                 # Time to wait before checking if we have an Internet connection (secs)
TIME_TO_MODEM_UP = 10             # Time to wait before starting 3G modem
WATCHDOG_INTERVAL = 30            # Time between manager checks (secs)
#MIN_TIME_BETWEEN_REBOOTS = 240   # Stops constant rebooting (secs)
MIN_TIME_BETWEEN_REBOOTS = 3600   # Stops constant rebooting (secs)
REBOOT_WAIT = 10                  # Time to allow bridge to stop before rebooting
RESTART_INTERVAL = 10             # Time between telling manager to stop and starting it again
EXIT_WAIT = 2                     # On SIGINT, time to wait before exit after manager signalled to stop
SAFETY_INTERVAL = 300             # Delay before rebooting if manager failed to start
CHECK_INTERFACE_DELAY = 900       # Time bewteen connection checks if not connected to Internet
NTP_UPDATE_INTERVAL = 12*3600     # How often to run ntpd to sync time

import sys
import signal
import time
import os
import glob
import procname
import wifisetup
from subprocess import call
from subprocess import Popen
from subprocess import check_output
from twisted.internet import threads
from twisted.internet import reactor, defer
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory
from cbconfig import *

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
        self.starting = True                    # Don't check manager watchdog when manager not running
        self.connecting = True                  # Ignore conduit not connected messages if trying to connect
        self.disconnected = False               # We are disconnected from the bridge controller
        self.timeStamp = time.time()            # Keeps track of when manager last communicated
        self.interfaceDownTime = time.time()    # Last time interface was known to be connected
        self.beginningOfTime = time.time()      # Used when making decisions about rebooting
        self.noServerCount = 0                  # Used when making decisions about rebooting
        self.interfaceChecks = 0                # Keeps track of how many times network connection has been checked
        self.checkingManager = False            # So that we knoow when checkManager method is active
        signal.signal(signal.SIGINT, self.signalHandler)  # For catching SIGINT
        signal.signal(signal.SIGTERM, self.signalHandler)  # For catching SIGTERM
        if not CB_DEV_BRIDGE:
            if CB_CELLULAR_BRIDGE:
                logging.info("%s  CB_CELLULAR_BRIDGE: %s", ModuleName, CB_CELLULAR_BRIDGE)
                reactor.callLater(TIME_TO_MODEM_UP, self.startModem)
            # Call checkInterface even if in cellular mode in case connected by eth0/wlan0 as well
            try:
                reactor.callLater(TIME_TO_IFUP, self.checkInterface)
            except:
                logging.error("%s Unable to call checkInterface", ModuleName)

        reactor.callLater(0.1, self.startManager, False)
        reactor.run()

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
        except:
            logging.error("%s Bridge manager failed to start: %s", ModuleName, exe)
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
                if not self.connecting or not self.disconnected:
                    self.connecting = True
                    self.disconnected = True
                    self.interfaceDownTime = time.time()
                    if CB_CELLULAR_BRIDGE:
                        reactor.callInThread(self.checkModem)
                    else:
                        self.recheckInterface()
            else:
                self.disconnected = False

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
                except:
                    logging.warning("%s Cannot send message to manager. Rebooting", ModuleName)
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

    def startModemThread(self):
        # Called in a thread
        if wifisetup.clientConnected():
            logging.debug("%s startModem. Already connected. Not starting modem", ModuleName)
            return
        logging.debug("%s startModem. Not connected. Starting modem", ModuleName)
        try:
            s = check_output(["sudo", "/usr/bin/sg_raw", "/dev/sr0", "11", "06", "20", "00", "00", "00", "00", "00", "01", "00"])
            logging.debug("%s startModem, sg_raw output: %s", ModuleName, s)
        except Exception as ex:
            logging.warning("%s startModem sg_raw call failed", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
        try:
            s = check_output(["dhclient", "eth1"])
            self.connecting = False
            logging.debug("%s startModem, dhclient eth1: %s, self.connecting: %s", ModuleName, s, self.connecting)
        except Exception as ex:
            logging.info("%s startModem dhclient failed on eth1, using sakis3g", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
            usbAddr = ""
            lsusb = check_output(["lsusb"]).split()
            logging.debug("%s StartModem, lsusb: %s", ModuleName, str(lsusb))
            for l in lsusb:
                if l[:4] == "12d1":
                    usbAddr = l[5:]
                    break
            if usbAddr != "":
                sakis3gConf = "/etc/sakis3g.conf"
                i = open(sakis3gConf, 'r')
                o = open("sakis3g.tmp", 'w') 
                found = False
                replaced = False
                for line in i:
                    logging.debug("%s startModem. line in:  %s", ModuleName, line)
                    if "USBMODEM" in line:
                        line = "USBMODEM=\"12d1:" + usbAddr + "\"\n"
                        logging.debug("%s startModem. Modem: %s", ModuleName, line)
                    o.write(line)
                i.close()
                o.close()
                call(["mv", "sakis3g.tmp", sakis3gConf])
            # Try to connect 6 times, each time increasing the waiting time
            for attempt in range (5):
                try:
                    # sakis3g requires --sudo despite being run by root. Config from /etc/sakis3g.conf
                    #s = check_output(["/usr/bin/sakis3g", "--sudo", "reconnect", "--debug"])
                    s = check_output(["/usr/bin/sakis3g", "--sudo", "reconnect", "--debug"])
                    logging.debug("%s startModem, attempt %s. s: %s", ModuleName, str(attempt), s)
                    if "connected" in s.lower() or "reconnected" in s.lower():
                        self.connecting = False
                        logging.info("%s startModem succeeded using sakis3g: %s, self.connecting: %s", ModuleName, s, self.connecting)
                        break
                except Exception as ex:
                    logging.warning("%s startModem sakis3g failed, attempt %s", ModuleName, str(attempt))
                    logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
                    time.sleep(attempt*60)
        try:
            # This is zwave.me
            ip_to_block = "46.20.244.72"
            s = check_output(["iptables", "-A", "INPUT", "-s", ip_to_block, "-j", "DROP"])
            s = check_output(["iptables", "-A", "OUTPUT", "-s", ip_to_block, "-j", "DROP"])
        except Exception as ex:
            logging.warning("%s iptables setup failed", ModuleName)
            logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))

    def checkModem(self):
        logging.info("%s checkModem", ModuleName)
        if time.time() - self.interfaceDownTime > MIN_TIME_BETWEEN_REBOOTS:
            logging.info("%s checkModem. Not connected for a very long time. Rebooting.", ModuleName)
            reactor.callFromThread(self.doReboot)
        else:
            reactor.callLater(CHECK_INTERFACE_DELAY, self.startModem) 

    def startModem(self):
        reactor.callInThread(self.startModemThread)

    def checkInterface(self):
        # Called only at start to check we have an Internet connection
        # Defer to thread - it could take several seconds
        logging.debug("%s checkInterface called", ModuleName)
        d1 = threads.deferToThread(wifisetup.checkInterface, startup=True, enableSwitch=(not CB_CELLULAR_BRIDGE))
        d1.addCallback(self.onInterfaceChecked)

    def onInterfaceChecked(self, mode):
        if mode == "none":
            if not CB_CELLULAR_BRIDGE:
                logging.info("%s onInterfaceChecked. Connected by %s", ModuleName, mode)
                logging.info("%s onInterfaceChecked. Not connected. Asking for SSID", ModuleName)
                d = threads.deferToThread(wifisetup.getConnected)
                d.addCallback(self.checkConnected)
        else:
            self.connecting = False
            logging.info("%s onInterfaceChecked, self.connecting: %s", ModuleName, self.connecting)

    def checkConnected(self, connected):
        # At this point reset self.connecting regardless & let recheckInterface process take over
        self.connecting = False
        logging.info("%s checkConnected, connected: %s, self.connecting: %s", ModuleName, connected, self.connecting)

    def recheckInterface(self):
        # Callled when manger is disconnected from the server
        logging.debug("%s recheckInterface", ModuleName)
        d1 = threads.deferToThread(wifisetup.checkInterface, startup=False, enableSwitch=(not CB_CELLULAR_BRIDGE))
        d1.addCallback(self.onInterfaceRechecked)

    def onInterfaceRechecked(self, mode):
        logging.info("%s onInterfaceRechecked. Connected by %s", ModuleName, mode)
        logging.debug("%s onInterfaceRechecked. time: %s, interfaceDownTime: %s", ModuleName, time.time(), self.interfaceDownTime)
        if mode == "none" or self.disconnected:
            if time.time() - self.interfaceDownTime > MIN_TIME_BETWEEN_REBOOTS:
                logging.info("%s onInterfaceRechecked. Not connected for a very long time. Rebooting.", ModuleName)
                reactor.callFromThread(self.doReboot)
            else:
                d1 = threads.deferToThread(wifisetup.switchwlan0, "client")
                d1.addCallback(self.onInterfaceReset)

    def onInterfaceReset(self, connected):
        logging.info("%s onInterfaceReset, connected: %s", ModuleName, connected)
        if self.disconnected:
            reactor.callLater(CHECK_INTERFACE_DELAY, self.recheckInterface)

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
        if not self.connecting:
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
            except:
                logging.info("%s Unable to reboot, probably because bridge not run as root", ModuleName)
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
