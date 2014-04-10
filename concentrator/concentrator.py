#!/usr/bin/env python
# concentrator.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
ModuleName = "Concentrator"

# Number of samples stored locally before a commit to Dropbox
DROPBOX_COMMIT_COUNT = 10
DROPBOX_START_DELAY = 20  # Time to wait before trying to connect to Dropbox

import sys
import time
import os
import json
import logging
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
from cbcommslib import CbClientProtocol
from cbcommslib import CbClientFactory
from cbcommslib import CbServerProtocol
from cbcommslib import CbServerFactory
from cbconfig import *
from dropbox.client import DropboxClient, DropboxOAuth2Flow, DropboxOAuth2FlowNoRedirect
from dropbox.rest import ErrorResponse, RESTSocketError
from dropbox.datastore import DatastoreError, DatastoreManager, Date, Bytes

class DataStore():
    def __init__(self):
        self.config = {}
        self.appData = {}
        self.enabled = False
        self.count = 0

    def setConfig(self, config):
        self.config = config

    def getConfig(self):
        return self.config

    def appendData(self, device, type, timeStamp, data):
        if self.enabled:
            self.appData[device].append({
                                         "type": type,
                                         "timeStamp": timeStamp,
                                         "data": data
                                       })
            self.count += 1

    def addDevice(self, d):
        self.appData[d] = []

    def deviceKnown(self, d):
        if d in self.appData:
            return True
        else:
            return False

    def getData(self, device):
        data = self.appData[device]
        self.appData[device] = [] 
        return data

    def getAllData(self):
        data = self.appData
        for d in self.appData:
            self.appData[d] = []
        self.count = 0
        return data

    def howBig(self):
        return self.count

    def enableOutput(self, enable):
        self.enabled = enable
        logging.info("%s enabledOutput: %s", ModuleName, self.enabled)

class DropboxStore():
    def __init__(self):
        self.configured = False
        self.connected = False
        self.gotConfig = False
        self.count = 0

    def connectDropbox(self, hostname):
        connected = True
        access_token = os.getenv('CB_DROPBOX_TOKEN', 'NO_TOKEN')
        logging.info("%s Dropbox access token: %s", ModuleName, access_token)
        try:
            self.client = DropboxClient(access_token)
        except:
            logging.error("%s Could not access Dropbox. Wrong access token?", ModuleName)
            connected = False
        else:
            self.manager = DatastoreManager(self.client)
            hostname = hostname.lower()
            logging.info("%s Datastore ID: %s", ModuleName, hostname)
            try:
                self.datastore = self.manager.open_or_create_datastore(hostname)
            except:
                logging.info("%s Could not open Dropbox datastore", ModuleName)
                connected = False
        self.connected = connected
        return self.connected

    def configure(self):
        idToName = self.config['idToName']
        t = self.datastore.get_table('config')
        for i in idToName:
            devName = idToName.get(i)
            t.get_or_insert(i, type='idtoname', device=i, name=devName)
        self.datastore.commit()
        self.configured = True

    def setConfig(self, config):
        self.config = config
        self.gotConfig = True
        if self.connected:
            self.configure()
    
    def appendData(self, device, type, timeStamp, data):
        if self.connected:
            if self.configured:
                devTable = self.datastore.get_table(device)
                date = Date(timeStamp)
                t = devTable.insert(Date=date, Type=type, Data=data)
                if self.count > DROPBOX_COMMIT_COUNT:
                    self.datastore.commit()
                    self.count = 0
                else:
                    self.count += 1
            elif self.gotConfig:
                self.configure()
    
class DevicePage(Resource):
    isLeaf = True
    def __init__(self, dataStore):
        self.dataStore = dataStore
        Resource.__init__(self)

    def _delayedRender(self, request):
        data = self.dataStore.getData(self.currentDev)
        if data == []:
            d = deferLater(reactor, 0.2, lambda: request)
            d.addCallback(self._delayedRender)
            return NOT_DONE_YET
        else:
            request.setHeader('Content-Type', 'application/json')
            response = {"device": self.currentDev,
                        "data": data}
            request.write(json.dumps(response))
            request.finish()

    def render_GET(self, request):
        reqParts = str(request).split(" ")
        # Botch until reason for differences is found
        if reqParts[0] == "<Request":
            self.currentDev = reqParts[4][12:]
        else:
            self.currentDev = reqParts[1][8:]
        try:
            data = self.dataStore.getData(self.currentDev)
        except:
            request.setHeader('Content-Type', 'application/json')
            #request.setHeader('Status', '404')
            response = {"device": self.currentDev,
                        "status": "Error. No data for device"}
            return json.dumps(response)
        if data == []:
            d = deferLater(reactor, 0.2, lambda: request)
            d.addCallback(self._delayedRender)
            return NOT_DONE_YET
        else:
            request.setHeader('Content-Type', 'application/json')
            response = {"device": self.currentDev,
                        "data": data}
            return json.dumps(response)

class ConfigPage(Resource):
    isLeaf = True
    def __init__(self, dataStore):
        self.dataStore = dataStore
        Resource.__init__(self)

    def render_GET(self, request):
        request.setHeader('Content-Type', 'application/json')
        config = self.dataStore.getConfig()
        response = {"config": config}
        return json.dumps(response)

    def render_POST(self, request):
        request.setHeader('Content-Type', 'application/json')
        req = json.loads(request.content.getvalue())
        try:
            self.dataStore.enableOutput(req["enable"])
            response = {"resp": "ok"}
        except:
            response = {"resp": "bad command"}
        return json.dumps(response)

class RootResource(Resource):
    isLeaf = False
    def __init__(self, dataStore):
        self.dataStore = dataStore
        Resource.__init__(self)
        self.putChild('config', ConfigPage(self.dataStore))
        self.putChild('device', DevicePage(self.dataStore))

class Concentrator():
    def __init__(self, argv):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.status = "ok"
        self.doStop = False
        self.conc_mode = os.getenv('CB_CONCENTRATOR', 'client')
        logging.info("%s CB_CONCENTRATOR = %s", ModuleName, self.conc_mode)

        if len(argv) < 3:
            logging.error("%s Improper number of arguments", ModuleName)
            exit(1)
        managerSocket = argv[1]
        self.id = argv[2]
        logging.info("%s Hello", ModuleName)

        self.dataStore = DataStore()

        # Connection to manager
        initMsg = {"id": self.id,
                   "type": "conc",
                   "status": "req-config"} 
        self.managerFactory = CbClientFactory(self.processManager, initMsg)
        self.managerConnect = reactor.connectUNIX(managerSocket, self.managerFactory, timeout=10)

        # Connection to conduit process
        initMsg = {"message": "status",
                   "body": "ready"}
        self.concFactory = CbClientFactory(self.processServerMsg, initMsg)
        self.jsConnect = reactor.connectTCP("localhost", 5000, self.concFactory, timeout=10)
        # Intermediate for UWE use
        if self.conc_mode == "server":
            self.uweListen = reactor.listenTCP(8881, Site(RootResource(self.dataStore)))

        if self.conc_mode == 'client':
            self.dataStore.enableOutput(False)

        # Connect to Dropbox
        if self.conc_mode == 'client':
            self.dropboxStore = DropboxStore()
            with open('/etc/hostname', 'r') as hostFile:
                self.hostname = hostFile.read()
                if self.hostname.endswith('\n'):
                    self.hostname = self.hostname[:-1]
            reactor.callLater(DROPBOX_START_DELAY, self.connectDropbox)

        reactor.run()

    def connectDropbox(self):
        d1 = threads.deferToThread(self.dropboxStore.connectDropbox, self.hostname)
        d1.addCallback(self.checkDropbox)
    
    def checkDropbox(self, connected):
        """ Will continually try to connect until it is connected. """
        logging.info("%s Connected to Dropbox: %s", ModuleName, connected)
        if not connected:
            logging.info("%s Dropbox connection failed. Trying again", ModuleName)
            reactor.callLater(DROPBOX_START_DELAY, self.connectDropbox)
        else:
            logging.info("%s Dropbox connection successful", ModuleName)
 
    def processConf(self, config):
        """Config is based on what apps are available."""
        logging.info("%s processConf: %s", ModuleName, config)
        if config != "no_apps":
            self.cbFactory = {}
            self.appInstances = []
            for app in config:
                iName = app["id"]
                if iName not in self.appInstances:
                    # Allows for reconfig on the fly
                    appConcSoc = app["appConcSoc"]
                    self.appInstances.append(iName)
                    self.cbFactory[iName] = CbServerFactory(self.processReq)
                    reactor.listenUNIX(appConcSoc, self.cbFactory[iName])

    def processServerMsg(self, msg):
        #logging.debug("%s Received from controller: %s", ModuleName, msg)
        msg["status"] = "control_msg"
        msg["id"] = self.id
        self.cbSendManagerMsg(msg)

    def processManagerMsg(self, msg):
        self.concFactory.sendMsg(msg)

    def processManager(self, cmd):
        logging.debug("%s Received from manager: %s", ModuleName, cmd)
        if cmd["cmd"] == "msg":
            self.processManagerMsg(cmd["msg"])
            msg = {"id": self.id,
                   "status": "ok"}
        elif cmd["cmd"] == "stop":
            self.doStop = True
            msg = {"id": self.id,
                   "status": "stopping"}
            reactor.callLater(0.2, self.stopReactor)
        elif cmd["cmd"] == "config":
            self.processConf(cmd["config"])
            msg = {"id": self.id,
                   "status": "ready"}
        elif cmd["cmd"] != "ok":
            msg = {"id": self.id,
                   "status": "unknown"}
        else:
            msg = {"id": self.id,
                   "status": "none"}
        self.cbSendManagerMsg(msg)

    def stopReactor(self):
        d1 = defer.maybeDeferred(self.jsConnect.disconnect)
        d2 = defer.maybeDeferred(self.managerConnect.disconnect)
        if self.conc_mode == "server":
            d3 = defer.maybeDeferred(self.uweListen.stopListening)
            d = defer.gatherResults([d1, d2, d3], consumeErrors=True)
        else:
            d = defer.gatherResults([d1, d2], consumeErrors=True)
        d.addCallback(self.goodbye)

    def goodbye(self, status):
        reactor.stop()
        logging.info("%s Bye. Status: %s", ModuleName, status)

    def cbSendMsg(self, msg, iName):
        self.cbFactory[iName].sendMsg(msg)

    def cbSendManagerMsg(self, msg):
        self.managerFactory.sendMsg(msg)

    def appInit(self, appID):
        """ Request delayed to give app time to configure. """
        resp = {"id": "conc",
                "resp": "config"}
        self.cbSendMsg(resp, appID)

    def processReq(self, req):
        """
        Processes requests from apps.
        Called in a thread and so it is OK if it blocks.
        Called separately for every app that can make requests.
        """
        if req["msg"] == "init":
            logging.info("%s Init from app %s", ModuleName, req['appID'])
            if req["appID"] == "app1":
                reactor.callLater(6, self.appInit, req["appID"])
        elif req["msg"] == "req":
            if req["verb"] == "post":
                if self.conc_mode == "server":
                    if req["channel"] == 1:
                        if req["body"]["msg"] == "services":
                            for s in req["body"]["services"]:
                                self.dataStore.addDevice(s["id"])
                                self.dataStore.setConfig(req["body"])
                        elif req["body"]["msg"] == "data":
                            if self.dataStore.deviceKnown(req["body"]["deviceID"]):
                                self.dataStore.appendData(req["body"]["deviceID"], req["body"]["type"], \
                                    req["body"]["timeStamp"], req["body"]["data"])
                else:  # client mode
                   if req["body"]["msg"] == "services":
                       for s in req["body"]["services"]:
                            self.dropboxStore.setConfig(req["body"])
                   elif req["body"]["msg"] == "data":
                        self.dropboxStore.appendData(req['body']['deviceID'], req['body']['type'], \
                                    req["body"]["timeStamp"], req["body"]["data"])
        else:
            pass

if __name__ == '__main__':
    concentrator = Concentrator(sys.argv)
