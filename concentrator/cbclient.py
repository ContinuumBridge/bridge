#!/usr/bin/env python
# concentrator.py
# Copyright (C) ContinuumBridge Limited, 2013-2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Mark Claydon
#
from cookielib import CookieJar
import json
from math import ceil
import random
import sys
from twisted.internet import ssl
from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent, CookieAgent
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer

from twisted.internet import reactor, defer
#from twisted.logger import Logger
#log = Logger()
#log.startLogging(sys.stdout)
import logging
import logging.handlers
from cbconfig import *

from zope.interface import implements

from conf import CB_ADDRESS, KEY, AUTH_PORT, AUTH_PROTOCOL, SOCKET_PORT, SOCKET_PROTOCOL, BRIDGE_AUTH_SUFFIX \
    , BRIDGE_SOCKET_SUFFIX, CLIENT_AUTH_SUFFIX, CLIENT_SOCKET_SUFFIX
from cbsocket import CBSocketFactory, CBClientProtocol

class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass

class BodyPrinter(Protocol):
    def __init__(self, finished):
        self.finished = finished
        self.remaining = 1024 * 10
        self.total_response = ""

    def dataReceived(self, bytes):
        if self.remaining:
            display = bytes[:self.remaining]
            self.total_response += display  # Append to our response.
            self.remaining -= len(display)

    def connectionLost(self, reason):
        # Finished receiving body
        self.finished.callback(self.total_response)

class CBClient(object):

    reactor = None

    factory = None

    connector = None

    auth_retry_num = 0

    auth_max_retries = -1

    auth_max_backoff = 300

    socket_backoff_factor = 2

    socket_max_backoff = 100

    def __init__(self, address=None, is_bridge=False
                 , key=None, reactor=reactor, logger=None):
        #self.connections = set()
        # Setup logging
        if logger:
            self.logger = logger
        else:
            format = "%(asctime)s %(levelname)s: %(name)s %(message)s"
            logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format=format)
            logger = self.logger = logging.getLogger('CBClient')
            #handler = logging.StreamHandler(sys.stdout)
            #handler.setLevel(logging.DEBUG)
            #formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            #handler.setFormatter(formatter)
            #logger.addHandler(handler)
            logger.info("Testing the logging")

        self.reactor = reactor
        self.auth_url = AUTH_PROTOCOL + "://" + CB_ADDRESS + ":" + str(AUTH_PORT) \
                            + (BRIDGE_AUTH_SUFFIX if is_bridge else CLIENT_AUTH_SUFFIX)
        self.auth_key = key if key else KEY
        self.socket_address = CB_ADDRESS
        self.socket_address_suffix = BRIDGE_SOCKET_SUFFIX if is_bridge else CLIENT_SOCKET_SUFFIX
        self.socket_port = SOCKET_PORT
        self.session_id = ""

        self.authenticate()

    def onConnect(self, response):
        # Override this
        self.logger.info("CBClient Connected to {0}".format(response.peer))

    def _onConnect(self, response):
        self.factory.resetDelay()
        self.onConnect(response)

    def onOpen(self):
        # Override this
        self.logger.info("CB Client open")

    def _onOpen(self):
        self.onOpen()

    def onMessage(self, response, isBinary):
        # Override this
        if isBinary:
            self.logger.info("CB Client binary message received: {0} bytes".format(len(response)))
        else:
            self.logger.info("CB Client message received: {0}".format(response.decode('utf8')))

    def _onMessage(self, response, isBinary):
        self.onMessage(response, isBinary)

    def onClose(self, wasClean, code, reason):
        # Override this
        self.logger.info("CB Client closed. Reason: {0}".format(reason))

    def _onClose(self, wasClean, code, reason):
        self.onClose(wasClean, code, reason)

    def authenticate(self):
        #self.session_id = cb_authenticate(self.auth_url)
        self.logger.info("Authenticating")
        cookieJar = CookieJar()
        agent = CookieAgent(Agent(self.reactor), cookieJar)
        data = '{"key": "' + self.auth_key + '"}'
        self.logger.info("self.auth_url is: {0}".format(self.auth_url))
        d = agent.request(
            'POST',
            self.auth_url,
            Headers({'User-Agent': ['Twisted Web Client Example'],
                     'content-type': ['application/json']}),
            StringProducer(data))
        d.addCallback(self.handleAuthResponse, cookieJar)
        d.addErrback(self.handleAuthFailed)

    def handleAuthFailed(self, reason):
        self.logger.warning("Authentication failed. Reason: {0}".format(reason))
        self.reauthenticate()

    def handleAuthResponse(self, response, cookieJar):
        finished = Deferred()
        if response:
            response.deliverBody(BodyPrinter(finished))
            finished.addCallback(self.handleAuthResponseBody, cookieJar)
        else:
            self.logger.warning("No response to authentication request")
            self.reauthenticate()

    def handleAuthResponseBody(self, bodyJSON, cookieJar):

        try:
            body = json.loads(bodyJSON)
        except ValueError, e:
            self.logger.error("Could not parse auth response. Reason: {0}".format(e))
            return self.reauthenticate()

        for cookie in cookieJar:
            if cookie.name == "sessionid":
                self.session_id = cookie.value
        if self.session_id:
            self.auth_retry_num = 0
            try:
                self.cbid = body['cbid']
            except KeyError:
                self.logger.warning("No cbid provided in auth response, sending messages will not work as expected")
            self.setupSocket()
        else:
            self.logger.warning("No session id in authentication response")
            self.reauthenticate()

    def reauthenticate(self):

        exp_backoff = pow(self.auth_retry_num, 2)
        backoff = min(ceil(exp_backoff * random.random()), self.auth_max_backoff)
        self.logger.info("Trying again in {0} seconds.".format(int(backoff)))
        self.auth_retry_num += 1
        self.reactor.callLater(backoff, self.authenticate)

    def setupSocket(self):

        headers = {'sessionid': self.session_id}

        socket_url = u"{0}://{1}{2}".format(SOCKET_PROTOCOL, self.socket_address
                                                , self.socket_address_suffix)

        factory = self.factory = CBSocketFactory(socket_url, headers=headers)
        factory.handleClientConnectionLost = self.handleFactoryConnectionLost

        factory.protocol = protocol = CBClientProtocol
        protocol.handleMessage = self._onMessage
        protocol.handleOpen = self._onOpen
        protocol.handleConnect = self._onConnect
        protocol.handleClose = self._onClose

        if AUTH_PROTOCOL == "https":
            self.logger.debug("Connecting using SSL")
            contextFactory = ssl.ClientContextFactory()
            self.connector = self.reactor.connectSSL(self.socket_address, self.socket_port, self.factory, contextFactory)
        else:
            self.logger.debug("Connecting without SSL")
            self.connector = self.reactor.connectTCP(self.socket_address, self.socket_port, self.factory)

    def sendMessage(self, destination, body):

        message = {
            'destination': destination,
            'source': self.cbid,
            'body': body
        }
        if self.factory.connected:
            self.logger.info("Sending message to {0}. Body: {1}".format(destination, body))
            #reactor.callFromThread(self.factory.sendMessage, json.dumps(message).encode('utf8'))
            reactor.callFromThread(self.factory.sendMessage, json.dumps(message))
        else:
            self.logger.warning("Could not send message to {0}" \
                                ", the connection is not open. Body: {1}".format(destination, body))

        return self.factory.connected

    def handleFactoryConnectionLost(self, factory, connector, reason):

        closeReason = factory.connection.wasNotCleanReason
        self.logger.info("Client socket connection lost. Reason: {0}".format(closeReason))

        if closeReason == "WebSocket connection upgrade failed (403 - Forbidden)":
            self.destroySocket()
            self.reauthenticate()
        else:
            factory.retry(connector)

    def destroySocket(self):

        self.factory.stopTrying()

        if self.connector:
            self.connector.disconnect()
            self.connector = None
