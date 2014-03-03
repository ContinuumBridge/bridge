# Include the Dropbox SDK
from dropbox.client import DropboxClient, DropboxOAuth2Flow, DropboxOAuth2FlowNoRedirect
from dropbox.rest import ErrorResponse, RESTSocketError
from dropbox.datastore import DatastoreError, DatastoreManager, Date, Bytes
from pprint import pprint
import time

access_token = 'yd0PQdjPz0sAAAAAAAAAAWoWEA1yPLVJ5BfBy4I9NKta-yJrb-UJPPtXeh4Emkgt'
client = DropboxClient(access_token)
print 'linked account: ', client.account_info()

manager = DatastoreManager(client)
datastore = manager.open_default_datastore()
#tasks_table = datastore.get_table('tasks')
#first_task = tasks_table.insert(taskname='Buy milk', completed=False)
#second_task = tasks_table.insert(taskname='Write Python', completed=False)
temps_table = datastore.get_table('temps')
t = time.time()
date = Date(t)
temp = temps_table.insert(Date=date, Temp=32.5)
time.sleep(1)
t = time.time()
date = Date(t)
temp = temps_table.insert(Date=date, Temp=35)
datastore.commit()

