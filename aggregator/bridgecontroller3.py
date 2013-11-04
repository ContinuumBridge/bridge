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
        self.watchTick = 0
        #w = threads.deferToThread(self.watchDog)
        self.adts = []
        self.appAdts = []
        self.config = {}

    def connectionMade(self):
        print "Connection made from Bridge"

    def connectionLost(self, reason):
        print "Bridge closed connection"

    def checkCmdThread(self):
        cmd = raw_input("Command > ")
        #print "Command was: ", cmd
        processed = False
        while not processed:
            if cmd == "exit":
                self.checkWatchDog = False
                time.sleep(1)
                reactor.stop()
                sys.exit
            elif cmd == "":
                cmd = raw_input("Command > ")
            elif cmd == "discover":
                msg  = {"cmd": cmd}
                self.sendLine(json.dumps(msg))
                processed = True
            elif cmd == "start" or cmd == "stop" or cmd == "stopapps" \
                         or cmd == "stopal;":
                msg  = {"cmd": cmd}
                self.sendLine(json.dumps(msg))
                cmd = raw_input("Command > ")
            else:
                print "Unrecognised input: ", cmd
                cmd = raw_input("Command > ")
            
    def checkCmd(self):
        d = threads.deferToThread(self.checkCmdThread)

    #def watchDog(self):
        #while self.checkWatchDog:
            #if time.time() - self.watchTime > 10:
                #print "No heartbeat from bridge for more than 10 seconds"
            #time.sleep(1)

    def processDiscovered(self, msg):
        if msg["num"] != 0:
            if msg["num"] > 1: 
                print("More than 1 device found. Processing only one")
            print ("Device - SensorTag: " + msg[str(0)][1])
            friendly = raw_input("Type friendly name  > ")
            gotPurpose = False
            while not gotPurpose:
                purpose = \
                    raw_input("Type purpose (fridge | door | activity  > ")
                if purpose != "fridge" and purpose != "door" \
                    and purpose != "activity":
                    print("Unrecognised purpose. Please re-enter.")
                else:
                    gotPurpose = True
            self.buildBridgeData(friendly, purpose, msg[str(0)][1]) 
        else:
            print("No devices found. Try again.")
            self.checkCmd()

    def buildBridgeData(self, friendly, purpose, btAddr):
        numAdts = len(self.adts)
        adtNum = numAdts + 1
        adt = {"name": "SensorTag",
              "id": "tag" + str(adtNum),
              "method": "btle",
              "btAddr": btAddr,
              "exe": '/home/pi/bridge/drivers/sensortagadaptor3.py',
              "mgrSoc": "/tmp/ManagerSocket" + str(adtNum),
              "apps": [
                  {"name": "living",
                   "id": "living",
                   "adtSoc": "/tmp/adtSocket" + str(adtNum)}],
              "btAdpt": "hci0"}
        self.adts.append(adt)

        appAdt = {"name": "SensorTag",
                  "id": "tag" + str(adtNum),
                  "friendlyName": friendly,
                  "purpose": purpose,
                  "adtSoc": "/tmp/adtSocket" + str(adtNum)}
        self.appAdts.append(appAdt)
 
        apps = [{"name": "living",
                 "id": "living",
                 "exe": "/home/pi/bridge/apps/living3.py",
                 "mgrSoc": "/tmp/livingManagerSocket",
                 "adts": self.appAdts, 
                 }]

        self.config = {"cmd": "config",
                       "bridge": {"id": 42,
                                  "friendly": "Friendly Bridge",
                                   "adpt": self.adts,
                                   "apps": apps}}
        self.sendLine(json.dumps(self.config))
    
    def lineReceived(self, rawMsg):
        #print "Message received: ", rawMsg
        self.watchTime = time.time()
        msg = json.loads(rawMsg)
        if msg["status"] == "ready":
            print "Bridge ready"
            self.checkCmd()
        elif msg["status"] == "discovered":
            print "Discovered devices:"
            pprint(msg)
            self.processDiscovered(msg)
            self.checkCmd()
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
    #print "Bridge socket: ", bridgeSoc

    bridgeSocFactory=Factory()
    bridgeSocFactory.protocol = BridgeControlProtocol

    try:
        reactor.listenTCP(int(bridgeSoc), bridgeSocFactory)
        print "Opened Bridge socket ", bridgeSoc
    except:
        print "Failed to open Bridge socket ", bridgeSoc

    reactor.run()
