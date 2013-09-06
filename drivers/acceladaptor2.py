#!/usr/bin/env python

import pexpect
import sys
import time
import os
import atexit
from signal import signal, SIGTERM
import pdb
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor

#from cbcomms import *

def initSensorTag(device, addr):
    cmd = 'gatttool -i ' + device + ' -b ' + addr + ' --interactive'
    print "Waiting for sensor tag"
    gatt = pexpect.spawn(cmd)
    gatt.expect('\[LE\]>')
    gatt.sendline('connect')
    gatt.expect('\[LE\]>')
    print "Connected to sensor tag"
    # Enable accelerometer
    gatt.sendline('char-write-cmd 0x31 01')
    gatt.expect('\[LE\]>')
    print "Enabled accelerometer"
    print "Enable notification"
    gatt.sendline('char-write-cmd 0x2e 0100')
    gatt.expect('\[LE\]>')
    print "Notification enabled"
    print "Changing reporting interval"
    gatt.sendline('char-write-cmd 0x34 0a')
    gatt.expect('\[LE\]>')
    print "Reporting interval changed"

    return gatt

def signExtend(a):
    if a > 127:
        a = a - 256
    return a

def getAccel(gatt):
    # Enable accelerometer
    gatt.sendline('char-write-cmd 0x31 01')
    gatt.expect('\[LE\]>')
    gatt.expect('value: .*')
    #print "Accelerometer data read"
    raw = gatt.after.split()
    a = signExtend(int(raw[1], 16))
    b = signExtend(int(raw[2], 16))
    c = signExtend(int(raw[3], 16))
    accel = str(a) + " " + str(b) + " " + str(c) 

    return accel

print "Hello from the twisted accelerometer adaptor"

if len(sys.argv) < 4:
    print "Usage: " + sys.argv[0] + " device bluetooth_address socket"
    exit(1)

#signal(SIGTERM, lambda signum, stack_frame: exit(1))

device = sys.argv[1]
addr = sys.argv[2]
socket = sys.argv[3]

os.system("sudo hciconfig " + device + " reset")

print "About to initSensorTag"
gatttool = initSensorTag(device, addr)
time.sleep(1)

print socket
f=Factory()
f.protocol = Accel
reactor.listenUNIX("/tmp/accelSocket", f, backlog=10)
reactor.run()

"""
while True:
    readChannel(ch)
    buffer = getChannelData(ch)
    # Get the required data and then send it
    if "accel" in buffer:
        setChannelData(ch, str(getAccel(gatttool)))
    else:
        setChannelData(ch, "unknown request")

    writeChannel(ch)
"""

