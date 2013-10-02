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
        self.watchTime = time.time()
        self.checkWatchDog = True
        d = threads.deferToThread(self.checkCmd)
        w = threads.deferToThread(self.watchDog)
        self.config = {}

    def connectionMade(self):
        print "Connection made from Bridge"

    def connectionLost(self, reason):
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
                    self.sendLine(json.dumps(msg))
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

    def processDiscovered(self, msg):
        """ For now, just hard-wire config for 1 SensorTag & 1 App """
        adts = {}
        if msg["num"] != 0:
            for d in range(msg["num"]):
                adt = {"name": msg[str(d)][0],
                      "method": "btle",
                      "btAddr": msg[str(d)][1],
                      "exe": '/home/pi/bridge/drivers/sensortagadaptor.py',
                      "mgrSoc": "/tmp/tag1ManagerSocket",
                      "numAppSoc": 1,
                      "appSocs": ["/tmp/tagAdtSocket1"],
                      "btAdpt": "hci0"}
                adts["adt1"] = adt

            apps = {"app1":
                   {"name": "living",
                    "exe": "/home/pi/bridge/apps/living.py",
                    "mgrSoc": "/tmp/livingManagerSocket",
                    "numAdtSocs": 1,
                    "adtSocs": ["/tmp/tagAdtSocket1"]}}
            self.config["cmd"] = "config"
            self.config["adpt"] = adts
            self.config["apps"] = apps
        else:
            self.config["cmd"] = "none"
        self.sendLine(json.dumps(self.config))

    def lineReceived(self, rawMsg):
        #print "Message received: ", rawMsg
        self.watchTime = time.time()
        msg = json.loads(rawMsg)
        if msg["status"] == "ready":
            print "Bridge ready"
        elif msg["status"] == "reqSync":
            print "Sync requested"
        elif msg["status"] == "discovered":
            print "Discovered devices:"
            pprint(msg)
            self.processDiscovered(msg)
        elif msg["status"] == "reqSync":
            print "Sync requested"
            self.sendLine(json.dumps(self.config))
        elif msg["status"] != "ok":
            print "Unknown message received from bridge" 
 
if __name__ == '__main__':
 
    if len(sys.argv) < 2:
        print "Usage: manager <bridge ip address>:<bridge socket>"
        exit(1)
    bridgeSoc = sys.argv[1]
    print "Bridge socket: ", bridgeSoc

    bridgeSocFactory=Factory()
    bridgeSocFactory.protocol = BridgeControlProtocol

    try:
        reactor.listenUNIX(bridgeSoc, bridgeSocFactory, backlog=4)
        print "Opened Bridge socket ", bridgeSoc
    except:
        print "Failed to open Bridge socket ", bridgeSoc

    reactor.run()
