import json
import sys
import time
from twisted.internet import threads
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor, defer
from twisted.protocols.basic import LineReceiver
from pprint import pprint
 
class BridgeControlProtocol(LineReceiver):
 
    def __init__(self):
        print "Assisted living monitor"

    def connectionMade(self):
        print "Connection made from Bridge"

    def connectionLost(self, reason):
        print "Bridge closed connection"

    def lineReceived(self, rawMsg):
        msg = json.loads(rawMsg)
        #print msg
        printStr = ""
        for t in msg:
            if t == "tag1":
                printStr += "%10s" % msg["tag1"]["friendlyName"]
                printStr += "  " + "%4.1f" % msg["tag1"]["ambT"]
                printStr += "  " + "%4.1f" % msg["tag1"]["objT"]
            if t == "tag2":
                printStr += "%10s" % msg["tag2"]["friendlyName"]
                printStr += "  " + "%4.1f" % msg["tag2"]["ambT"]
                printStr += "  " + "%4.1f" % msg["tag2"]["objT"]
            if t == "event":
                #printStr += "  Event " + str(msg["event"])
                printStr += "  Event " + "%10s" % msg["event"]["name"] 
                printStr += "  " + "%4d" % msg["event"]["energy"]
        print printStr

if __name__ == '__main__':
 
#    if len(sys.argv) < 2:
#        print "Usage: manager <bridge ip address>:<bridge socket>"
#        exit(1)
#    bridgeSoc = sys.argv[1]

    bridgeSocFactory=Factory()
    bridgeSocFactory.protocol = BridgeControlProtocol

    try:
        reactor.listenTCP(3123, bridgeSocFactory)
        print "Opened Bridge socket "
    except:
        print "Failed to open Bridge socket "

    reactor.run()
