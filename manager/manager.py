#!/usr/bin/env python

import sys
import time
import os
import subprocess
import json
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor, defer

def callback_func(result):
    print result
    reactor.stop
    return 

print "Hello from the Bridge Manager"

# Start an app
proc1 = subprocess.Popen(["/home/pi/bridge/drivers/acceladaptor2.py", "hci0", "90:59:AF:04:2B:92", "/tmp/accelSocket"])
print "Manager has started adaptor"
time.sleep(7)
proc2 = subprocess.Popen("/home/pi/bridge/apps/accelapp2.py")
print "Manager has started app"

d = defer.Deferred()
reactor.callLater(10, d.callback, "Manager has finished its job")
d.addCallback(callback_func)
reactor.run()


