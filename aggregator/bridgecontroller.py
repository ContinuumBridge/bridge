import json
import sys
import time
from twisted.internet import reactor
from twisted.internet import threads
from autobahn.websocket import WebSocketServerFactory, \
                               WebSocketServerProtocol, \
                               listenWS
 
class BridgeControlProtocol (WebSocketServerProtocol):
 
    def __init__(self):
        self.watchTime = time.time()
        self.checkWatchDog = True
        d = threads.deferToThread(self.checkCmd)
        w = threads.deferToThread(self.watchDog)

    #def onOpen(self):
        #d = threads.deferToThread(self.checkCmd)

    def onClose(self, wasClean, code, reason):
        print "Bridge closed connection"

    def checkCmd(self):
        process = True
        while process:
            try:
                cmd = raw_input("Command> ")
                #print "Command was: ", cmd
                if cmd == "exit":
                    process = False
                else:
                    msg  = {"cmd": cmd}
                    self.sendMessage(json.dumps(msg))
            except:
                print "Problem with command processing"
        self.checkWatchDog = False
        reactor.stop()
        sys.exit
    
    def watchDog(self):
        while self.checkWatchDog:
            if time.time() - self.watchTime > 5:
                print "No heartbeat from bridge for more than 5 seconds"
            time.sleep(5)
        
    def onMessage(self, rawMsg, binary):
        #print "Message received: ", rawMsg
        self.watchTime = time.time()
        msg = json.loads(rawMsg)
        if msg["status"] == "ready":
            print "Bridge ready"
        elif msg["status"] == "reqSync":
            print "Sync requested"
        elif msg["status"] == "discovered":
            print "Discovered devices"
            print msg
        elif msg["status"] != "ok":
            print "Unknown message received from bridge" 
 
if __name__ == '__main__':
 
    factory = WebSocketServerFactory("ws://192.168.0.19:9000", debug = False)
    factory.protocol = BridgeControlProtocol
    listenWS(factory)
    reactor.run()
