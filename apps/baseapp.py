#!/usr/bin/python
import sys
import os.path
import time
from cbcomms import *

# Sockets are named in/out as seen by the app
theapp = os.path.basename(sys.argv[0])
print "Name:"+theapp

nchannels = openAppChannels(theapp)
for ch in range(0, nchannels):
    initClientChannel(ch)

while True:
    for ch in range(0, nchannels):
        if isInputChannel(ch):
            readChannel(ch)
            buffer = getChannelData(ch)
            print "App received data from"+getChannelName(ch)+" ["+buffer+"]"

    for ch in range(0, nchannels):
        if isOutputChannel(ch):
            print "App sent data to "+getChannelName(ch)+" ["+buffer+"]"
            setChannelData(ch, buffer)
            writeChannel(ch)

    time.sleep(1)

for ch in range(0, nchannels):
    closeChannel(ch)
