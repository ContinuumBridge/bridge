# Include the Dropbox SDK
from dropbox.client import DropboxClient, DropboxOAuth2Flow, DropboxOAuth2FlowNoRedirect
from dropbox.rest import ErrorResponse, RESTSocketError
from dropbox.datastore import DatastoreError, DatastoreManager, Date, Bytes
from pprint import pprint
import time

access_token = 'yd0PQdjPz0sAAAAAAAAAAWoWEA1yPLVJ5BfBy4I9NKta-yJrb-UJPPtXeh4Emkgt'
client = DropboxClient(access_token)

manager = DatastoreManager(client)
ds = manager.list_datastores()
datastore = manager.open_default_datastore()
devTable = datastore.get_table('dev1')
ir_temps = devTable.query(Type='ir_temperature')
values = []
for t in ir_temps:
    #timeStamp = Date.to_datetime_local(t.get('Date'))
    timeStamp = float(t.get('Date'))
    temp = t.get('Data')
    values.append([timeStamp, temp])
values.sort(key=lambda tup: tup[0])
for v in values:
    print v[0], v[1]
