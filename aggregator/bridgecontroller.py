import json
from twisted.internet import reactor
from autobahn.websocket import WebSocketServerFactory, \
                               WebSocketServerProtocol, \
                               listenWS
 
 
class BridgeControlProtocol (WebSocketServerProtocol):
 
    def onMessage(self, rawMsg, binary):
        response = {}
        print "Message received: ", rawMsg
        msg = json.loads(rawMsg)
        if msg["status"] == "ready":
            print "Bridge ready"
            response["cmd"] = "start"
            self.sendMessage(json.dumps(response), binary)
        else:
            print "Unknown message received from bridge" 
 
if __name__ == '__main__':
 
    factory = WebSocketServerFactory("ws://192.168.0.19:9000", debug = False)
    factory.protocol = BridgeControlProtocol
    listenWS(factory)
    reactor.run()
