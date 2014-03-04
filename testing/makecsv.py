#!/usr/bin/env python
# makecvs.py
# Copyright (C) ContinuumBridge Limited, 2013-14 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
SENSORS = ['ir_temperature']


# Include the Dropbox SDK
from dropbox.client import DropboxClient, DropboxOAuth2Flow, DropboxOAuth2FlowNoRedirect
from dropbox.rest import ErrorResponse, RESTSocketError
from dropbox.datastore import DatastoreError, DatastoreManager, Date, Bytes
from pprint import pprint
import time
import os, sys

class MakeCVS():
    def __init__(self, argv):
        if len(argv) < 2:
            print "Usage: makecvs <bridge name> "
            exit(1)
        self.bridge  = argv[1]
        self.bridge = self.bridge.lower()
        print "Writing cvs files for ", self.bridge

        access_token = os.getenv('CB_DROPBOX_TOKEN', 'NO_TOKEN')
        print "Dropbox access token = ", access_token
        try:
            self.client = DropboxClient(access_token)
        except:
            print "Could not access Dropbox. Wrong access token?"
            exit()
        
        self.manager = DatastoreManager(self.client)
        self.ds = self.manager.open_or_create_datastore(self.bridge)
        self.process()
    
    def niceTime(self, timeStamp):
        localtime = time.localtime(timeStamp)
        milliseconds = '%03d' % int((timeStamp - int(timeStamp)) * 1000)
        now = time.strftime('%Y:%m:%d, %H:%M:%S:', localtime) + milliseconds
        return now

    def process(self):
        idToName = {}
        devTable = {}
        ir_temps = []
        t = self.ds.get_table('config')
        devices = t.query(type='idtoname')
        for d in devices:
            idToName[d.get('device')] = d.get('name')
        print "idToName: ", idToName
        for d in idToName:
            fileName = d + ".csv"
            self.f = open(fileName, "w", 0)
            t = self.ds.get_table(d)
            temps = t.query(Type='ir_temperature')
            values = []
            for t in temps:
                timeStamp = float(t.get('Date'))
                temp = t.get('Data')
                values.append([timeStamp, temp])
            values.sort(key=lambda tup: tup[0])
            for v in values:
                line = self.niceTime(v[0]) + "," + str("%2.1f" %v[1]) + "\n"
                self.f.write(line)

if __name__ == '__main__':
    m = MakeCVS(sys.argv)
