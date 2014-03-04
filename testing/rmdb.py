#!/usr/bin/env python
# rmdb.py
# Copyright (C) ContinuumBridge Limited, 2013-14 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
# Include the Dropbox SDK
from dropbox.client import DropboxClient, DropboxOAuth2Flow, DropboxOAuth2FlowNoRedirect
from dropbox.rest import ErrorResponse, RESTSocketError
from dropbox.datastore import DatastoreError, DatastoreManager, Date, Bytes
import dropbox.datastore 
from pprint import pprint
import time, sys, os
#
if len(sys.argv) < 2:
    print "Usage: makecvs <bridge name> "
    exit(1)
bridge  = sys.argv[1]
bridge = bridge.lower()
print "Deleting Dropbox datastore for ", bridge

access_token = os.getenv('CB_DROPBOX_TOKEN', 'NO_TOKEN')
print "Dropbox access token = ", access_token
try:
    client = DropboxClient(access_token)
except:
    print "Could not access Dropbox. Wrong access token?"
    exit()
 
manager = dropbox.datastore.DatastoreManager(client)
ds = manager.list_datastores()
manager.delete_datastore(bridge)

