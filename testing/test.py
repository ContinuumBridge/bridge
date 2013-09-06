#!/sr/bin/python
import sys
import os
#from twisted.protocols import protocol
from twisted.internet import protocol
import twisted.protocols
from twisted.internet import main, tcp

class Echo(protocol.Protocol):
    def dataReceived(self, data):
        self.transport.write(data)

factory = protocol.Factory()
factory.protocol = Echo
port = tcp.Port(8000, factory)
app = main.Application("echo")
app.addPort(port)
app.run()
