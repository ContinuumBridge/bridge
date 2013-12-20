from twisted.internet import reactor
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import UNIXClientEndpoint

class Greeter(Protocol):
    def sendMessage(self, msg):
        print "Sending message"
        self.transport.write("MESSAGE %s\r\n" % msg)

def gotProtocol(p):
    print "gotProtocol"
    p.sendMessage("Hello \r\n")
    reactor.callLater(1, p.sendMessage, "This is sent in a second")
    reactor.callLater(2, p.transport.loseConnection)

factory = Factory()
factory.protocol = Greeter
point = UNIXClientEndpoint(reactor, "tmpSoc")
d = point.connect(factory)
d.addCallback(gotProtocol)
print "point = ", point
