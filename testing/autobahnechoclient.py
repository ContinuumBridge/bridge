from twisted.internet import reactor, task
from autobahn.websocket import WebSocketClientFactory, \
                               WebSocketClientProtocol, \
                               connectWS
 
 
class EchoClientProtocol(WebSocketClientProtocol):
 
   def sendHello(self):
      self.sendMessage("Hello, world!")
 
   def onOpen(self):
      self.sendHello()
 
   def onMessage(self, msg, binary):
      print "Got echo: " + msg
      reactor.callLater(1, self.sendHello)
 
def runEverySecond():
    print "A second has passed"

 
if __name__ == '__main__':
 
    l = task.LoopingCall(runEverySecond)
    l.start(1.0) # call every second

    factory = WebSocketClientFactory("ws://192.168.0.15:9000", debug = False)
    factory.protocol = EchoClientProtocol
    connectWS(factory)
    reactor.run()
