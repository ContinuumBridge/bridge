import json
import sys
import time
from twisted.internet import reactor
from twisted.internet import threads
from autobahn.websocket import WebSocketServerFactory, \
                               WebSocketServerProtocol, \
                               listenWS
from pprint import pprint
 
class BridgeControlProtocol (WebSocketServerProtocol):
 
    def __init__(self):
        self.watchTime = time.time()
        self.checkWatchDog = True
        d = threads.deferToThread(self.checkCmd)
        w = threads.deferToThread(self.watchDog)
        self.config = {}

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
        self.sendMessage(json.dumps(self.config))

    def onMessage(self, rawMsg, binary):
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
            self.sendMessage(json.dumps(self.config))
        elif msg["status"] != "ok":
            print "Unknown message received from bridge" 
 
if __name__ == '__main__':
 
    if len(sys.argv) < 2:
        print "Usage: manager <bridge ip address>:<bridge socket>"
        exit(1)
    bridge = "ws://" + sys.argv[1]
    print "Bridge = ", bridge

    factory = WebSocketServerFactory(bridge, debug = False)
    factory.protocol = BridgeControlProtocol
    listenWS(factory)
    reactor.run()
