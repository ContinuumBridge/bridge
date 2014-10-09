import sys
import os.path
import time
import json
import logging
import procname
from twisted.internet.protocol import Protocol, Factory
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ClientFactory
from twisted.internet.protocol import ReconnectingClientFactory
ModuleName = "testlib" 
LineReceiver.MAX_LENGTH = 65535

class CbTestClientProtocol(LineReceiver):
    def __init__(self, processMsg, initMsg):
        self.processMsg = processMsg
        self.initMsg = initMsg

    def lineLengthExceeded(self, data):
        logging.debug("%s Maximum line length exceeded", ModuleName)

    def connectionLost(self, reason):
        logging.debug("%s Connection lost: %s", ModuleName, reason)

    def connectionMade(self):
        self.sendLine(json.dumps(self.initMsg))
        logging.debug("%s Connecction made", ModuleName)

    def lineReceived(self, data):
        logging.debug("%s Line received, start: %s", ModuleName, data[:100])
        logging.debug("%s Line received, end: %s", ModuleName, data[-100:])
        self.processMsg(json.loads(data))

    def sendMsg(self, msg):
        logging.debug("%s sending: %s", ModuleName, msg)
        self.sendLine(json.dumps(msg))

class CbTestClientFactory(ReconnectingClientFactory):
    def __init__(self, processMsg, initMsg):
        self.processMsg = processMsg
        self.initMsg = initMsg

    def buildProtocol(self, addr):
        self.proto = CbTestClientProtocol(self.processMsg, self.initMsg)
        return self.proto

    def sendMsg(self, msg):
        self.proto.sendMsg(msg)

    def clientConnectionLost(self, connector, reason):
        logging.debug("%s factory connection lost: %s", ModuleName, reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        logging.debug("%s factory connection lost: %s", ModuleName, reason)
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)
