#!/usr/bin/env python
# wemoadaptor.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "WeMo"

import sys
import time
import os
import logging
from cbcommslib import CbAdaptor
from cbconfig import *
from twisted.internet import threads
from twisted.internet import reactor
from ouimeaux.environment import Environment

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        #CbAdaptor methods processReq & cbAdtConfig MUST be subclassed
        CbAdaptor.processReq = self.processReq
        CbAdaptor.cbAdtConfigure = self.configure
        self.apps = []
        #CbAdaprot.__init__ MUST be called
        CbAdaptor.__init__(self, argv)

    def states(self, action):
        if self.state == "idle":
            if action == "connected":
                self.state = "connected"
            elif action == "inUse":
                self.state = "inUse"
        elif self.state == "connected":
            if action == "inUse":
                self.state = "activate"
        elif self.state == "inUse":
            if action == "connected":
                self.state = "activate"
        if self.state == "activate":
            if not self.accelApps:
                # No apps are using this switch
                logging.info("%s %s No apps using switch", ModuleName, self.id)
            elif self.sim == 0:
                logging.debug("%s %s Activated", ModuleName, self.id)
            self.state = "running"
        logging.debug("%s %s state = %s", ModuleName, self.id, self.state)

    def init(self):
        logging.info("%s %s %s Init", ModuleName, self.id, self.friendly_name)
        env = Environment()
        env.start()
        devices = env.list_switches()
        logging.info("%s %s %s devices: %s", ModuleName, self.id, self.friendly_name, devices)
        switch = env.get_switch(devices[0])
        state = switch.get_state()
        logging.info("%s %s %s state: %s", ModuleName, self.id, self.friendly_name, state)
        self.states(connected)

    def reportState(self, state):
        msg = {"id": self.id,
               "timeStamp": time.time(),
               "content": "switch_state",
               "data": state}
        for a in self.apps:
            reactor.callFromThread(self.cbSendMsg, msg, a)

    def processCommand(self, command):

        def onOff(self, numState):
            if numState == "1":
                return "on"
            else:
                return "off"

        # If at first it doesn't succeed, try again.
        for i in range(2):
            if command == "on":
                switch.on()
                state = onOff(switch.get_state())
                if state == "on":
                    break
            elif command == "off":
                switch.off()
                state = onOff(switch.get_state())
                if state == "off":
                    break
        self.reportState(state)

    def processReq(self, req):
        """
        Processes requests from apps.
        Called in a thread and so it is OK if it blocks.
        Called separately for every app that can make requests.
        """
        logging.debug("%s %s %s processReq, req = %s", ModuleName, self.id, self.friendly_name, req)
        tagStatus = "ok"
        if req["req"] == "init":
            resp = {"name": self.name,
                    "id": self.id,
                    "status": tagStatus,
                    "services": [{"parameter": "switch",
                                  "type": "mains_electic",
                                  "purpose": "heater"}],
                    "content": "services"}
            self.cbSendMsg(resp, req["id"])
        elif req["req"] == "services":
            # Apps may turn on or off services from time to time
            # So it is necessary to be able to remove as well as append.
            # Can't just destory the lists as they may be being used elsewhere
            if req["id"] not in self.apps:
                if "switch" in req["services"]:
                    self.apps.append(req["id"])  
            else:
                if "switch" not in req["services"]:
                    self.apps.remove(req["id"])  
        elif req["req"] == "command":
            self.processCommand(req["command"])

    def configure(self, config):
        """Config is based on what apps are to be connected.
            May be called again if there is a new configuration, which
            could be because a new app has been added.
        """
        if not self.configured:
            if self.sim != 0:
                self.simValues = SimValues()
            self.init()
            self.configured = True
            self.status = "configured"

if __name__ == '__main__':
    adaptor = Adaptor(sys.argv)

