#!/usr/bin/env python

import pexpect
import sys
import time
import os
import atexit
from signal import signal, SIGTERM
import pdb

from cbcomms import *

def s16tofloat(s16):
    f = float.fromhex(s16)
    if f > 32767:
        f -= 65535
    return f

# From http://processors.wiki.ti.com/index.php/SensorTag_User_Guide#Gatt_Server
#
#/* Conversion algorithm for die temperature */
#
#double calcTmpLocal(uint16 rawT) {
#
# //-- calculate die temperature [degrees C] --
# m_tmpAmb = (double)((qint16)rawT)/128.0; // Used in also in the calc. below
#
# return m_tmpAmb;
#
#}
#
#/* Conversion algorithm for target temperature */
#
#double calcTmpTarget(uint16 rawT) {
#
# //-- calculate target temperature [degrees C] -
# double Vobj2 = (double)(qint16)rawT;
# Vobj2 *= 0.00000015625;
#
# double Tdie2 = m_tmpAmb + 273.15;
# const double S0 = 6.4E-14;            // Calibration factor
#
# const double a1 = 1.75E-3;
# const double a2 = -1.678E-5;
# const double b0 = -2.94E-5;
# const double b1 = -5.7E-7;
# const double b2 = 4.63E-9;
# const double c2 = 13.4;
# const double Tref = 298.15;
# double S = S0*(1+a1*(Tdie2 - Tref)+a2*pow((Tdie2 - Tref),2));
# double Vos = b0 + b1*(Tdie2 - Tref) + b2*pow((Tdie2 - Tref),2);
# double fObj = (Vobj2 - Vos) + c2*pow((Vobj2 - Vos),2);
# double tObj = pow(pow(Tdie2,4) + (fObj/S),.25);
# tObj = (tObj - 273.15);
#
# return tObj;
#
#}

def initSensorTag(device, addr):
    cmd = 'gatttool -i ' + device + ' -b ' + addr + ' --interactive'
    print "Waiting for sensor tag"
    gatt = pexpect.spawn(cmd)
    gatt.expect('\[LE\]>')
    gatt.sendline('connect')
    gatt.expect('\[LE\]>')
    print "Connected to sensor tag"
    return gatt

def getAmbientTemperature(gatt):
    # Enable temperature sensor
    gatt.sendline('char-write-cmd 0x29 01')
    gatt.expect('\[LE\]>')
    time.sleep(1)
    gatt.sendline('char-read-hnd 0x25')
    gatt.expect('descriptor: .*')
    raw = gatt.after.split()
    objT = s16tofloat(raw[2] + raw[1])
    ambT = s16tofloat(raw[4] + raw[3]) / 128.0
    # Disable temperature sensor
    gatt.sendline('char-write-cmd 0x29 00')
    gatt.expect('\[LE\]>')

    return ambT

def getObjectTemperature(gatt):
    # Enable temperature sensor
    gatt.sendline('char-write-cmd 0x29 01')
    gatt.expect('\[LE\]>')
    time.sleep(1)
    gatt.sendline('char-read-hnd 0x25')
    gatt.expect('descriptor: .*')
    raw = gatt.after.split()
    objT = s16tofloat(raw[2] + raw[1]) * 0.00000015625
    ambT = s16tofloat(raw[4] + raw[3]) / 128.0
    # Disable temperature sensor
    gatt.sendline('char-write-cmd 0x29 00')
    gatt.expect('\[LE\]>')

    Tdie2 = ambT + 273.15
    S0 = 6.4E-14
    a1 = 1.75E-3
    a2 = -1.678E-5
    b0 = -2.94E-5
    b1 = -5.7E-7
    b2 = 4.63E-9
    c2 = 13.4
    Tref = 298.15

    S = S0 * (1 + a1 * (Tdie2 - Tref) + a2 * pow((Tdie2 - Tref), 2))
    Vos = b0 + b1 * (Tdie2 - Tref) + b2 * pow((Tdie2 - Tref), 2)
    fObj = (objT - Vos) + c2 * pow((objT - Vos), 2)
    objT = pow(pow(Tdie2,4) + (fObj/S), .25)
    objT -= 273.15

    return objT

def cleanup():
    print sys.argv[0] + " cleanup started"
    try:
        gatttool
    except NameError:
        print "Connection not setup"
    else:
        if gatttool.isalive():
            gatttool.kill(0)

print "Hello from the Python device adaptor"
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

while True:
    readChannel(ch)
    buffer = getChannelData(ch)
    # Get the required data and then send it
    if "ambtemp" in buffer:
        setChannelData(ch, str(getAmbientTemperature(gatttool)))
    elif "objtemp" in buffer:
        setChannelData(ch, str(getObjectTemperature(gatttool)))
    else:
        setChannelData(ch, "unknown request")

    writeChannel(ch)

closeChannel(ch)
print "Device closed down"
