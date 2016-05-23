
from autobahn.twisted.websocket import WebSocketClientProtocol, WebSocketClientFactory
from twisted.internet.protocol import ClientFactory, ReconnectingClientFactory

class CBClientProtocol(WebSocketClientProtocol):

    def __init__(self, *args, **kwargs):
        self.factory = kwargs.pop('factory', None)
        super(CBClientProtocol, self).__init__(*args, **kwargs)
        if self.factory is not None:
            self.factory.connection = self

    def onConnect(self, response):
        self.factory.resetDelay()
        self.handleConnect(response)

    def onOpen(self):
        self.handleOpen()

    def onMessage(self, message, isBinary):
        self.handleMessage(message, isBinary)

    def onClose(self, wasClean, code, reason):
        self.handleClose(wasClean, code, reason)


class CBSocketFactory(WebSocketClientFactory, ReconnectingClientFactory):

    connection = None

    @property
    def connected(self):
        try:
            return self.connection.state == CBClientProtocol.STATE_OPEN
        except AttributeError:
            return False

    def buildProtocol(self, addr):
        p = self.protocol(factory=self)
        return p

    def sendMessage(self, data):
        #for connection in self.connections:
        self.connection.sendMessage(data)

    def clientConnectionLost(self, connector, reason):
        #self.connection = None
        self.handleClientConnectionLost(self, connector, reason)
