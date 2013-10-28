#!/usr/bin/env python

import pexpect
import sys
import time
import os
import atexit
from signal import signal, SIGTERM
import pdb
import json
import pprint

from cbcomms import *

def s16tofloat(s16):
    f = float.fromhex(s16)
    if f > 32767:
        f -= 65535
    return f

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
    #time.sleep(0.01)
    #print "Reading accelerometer data"
    #gatt.sendline('char-read-hnd 0x2D')
    #gatt.expect('descriptor: .*')
    gatt.expect('value: .*')
    #print "Accelerometer data read"
    raw = gatt.after.split()
    #print "raw = ", raw
    #print "Raw values: ", raw[1], raw[2], raw[3]
    a = signExtend(int(raw[1], 16))
    b = signExtend(int(raw[2], 16))
    c = signExtend(int(raw[3], 16))
    accel = str(a) + " " + str(b) + " " + str(c) 
    #print "accel: ", a, b, c
    # Disable accelerometer
    #print "Disabling accelerometer"
    #gatt.sendline('char-write-cmd 0x29 00')
    #gatt.expect('\[LE\]>')

    return accel

def cleanup():
    print sys.argv[0] + " cleanup started"
    try:
        gatttool
    except NameError:
        print "Connection not setup"
    else:
        if gatttool.isalive():
            gatttool.kill(0)

print "Hello from the Python accelerometer adaptor"
# PYTHONPATH=../build/lib ./sensortagtemp.py hci1 90:59:AF:04:2B:92 ab:inport

if len(sys.argv) < 4:
    print "Usage: " + sys.argv[0] + " device bluetooth_address socket"
    exit(1)

atexit.register(cleanup)
signal(SIGTERM, lambda signum, stack_frame: exit(1))

device = sys.argv[1]
addr = sys.argv[2]
socket = sys.argv[3]

#pdb.set_trace()

os.system("sudo hciconfig " + device + " reset")

print socket
ch = openChannel(socket)
print "Driver channel = ", ch
initServerChannel(ch)

print "About to initSensorTag"
gatttool = initSensorTag(device, addr)
time.sleep(1)

while True:
    readChannel(ch)
    buffer = getChannelData(ch)
    action = json.loads(buffer)
    print "JSON:"
    pprint (action)
    # Get the required data and then send it
    #if "accel" in buffer:
    setChannelData(ch, str(getAccel(gatttool)))
    #else:
    #    setChannelData(ch, "unknown request")

    writeChannel(ch)

closeChannel(ch)
print "Device closed down"
