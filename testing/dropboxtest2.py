# Include the Dropbox SDK
from dropbox.client import DropboxClient, DropboxOAuth2Flow, DropboxOAuth2FlowNoRedirect
from dropbox.rest import ErrorResponse, RESTSocketError
#from dropbox.datastore import DatastoreError, DatastoreManager, Date, Bytes
import dropbox.datastore 
from pprint import pprint
import time

access_token = 'yd0PQdjPz0sAAAAAAAAAAWoWEA1yPLVJ5BfBy4I9NKta-yJrb-UJPPtXeh4Emkgt'
client = DropboxClient(access_token)
print 'linked account: ', client.account_info()

manager = dropbox.datastore.DatastoreManager(client)
ds = manager.list_datastores()
print "ds = ", ds
#datastore = manager.open_default_datastore()
#manager.delete_datastore('cbr-7')
manager.delete_datastore('cbrtest')

