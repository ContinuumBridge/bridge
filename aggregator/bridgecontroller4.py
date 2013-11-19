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
        self.devs = []
        self.appDevs = []
        self.apps = []
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
        numDevs = len(msg["devices"])
        if numDevs != 0:
            if numDevs > 1: 
                print("More than 1 device found. Processing only one")
            currentDev = msg["devices"][0]
            #print ("Device - SensorTag: " + msg[str(0)][1])
            print "Device - SensorTag: ", currentDev
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
            self.buildBridgeData(friendly, purpose, currentDev) 
        else:
            print("No devices found. Try again.")
            self.checkCmd()

    def buildBridgeData(self, friendly, purpose, currentDev):
        numDevs = len(self.devs)
        devNum = numDevs + 1
        dev = {"name": currentDev["name"],
               "friendlyName": friendly,
               "id": "dev" + str(devNum),
               "method": currentDev["method"],
               "btAddr": currentDev["addr"],
               "adt": {"name": "CB SensorTag Adt",
                       "provider": "ContinuumBridge",
                       "version": 2,
                       "url": "www.continuumbridge.com/adt/cbSensorTagAdtV2",
                       "exe": 'testSensorTagAdaptor.py',
                       "resource_uri": "/api/V1/device/" + str(devNum)
                      }
              }
        self.devs.append(dev)

        appDev = {
                      "resource_uri": "/api/V1/device/" + str(devNum)
                 } 
        self.appDevs.append(appDev)
 
        numApps = len(self.apps)
        if numApps == 0:
            appNum = numApps + 1
            app = {"id": "app" + str(appNum),
                   "name": "living",
                   "provider": "ContinuumBridge",
                   "version": 2,
                   "url": "www.continuumbridge.com/apps/cbLivingV2",
                   "exe": "living4.py",
                   "devices": self.appDevs,
                   "resource_uri": "/api/v1/app/" + str(appNum)
                  }
            self.apps.append(app)
    
        self.config = {"cmd": "config",
                       "bridge": {"id": 42,
                                  "friendlyName": "Friendly Bridge",
                                  "bridgeManager": "manager8.py",
                                  "backupManager": "manager7.py",
                                  "devices": self.devs,
                                  "apps": self.apps
                                 }
                      }
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
