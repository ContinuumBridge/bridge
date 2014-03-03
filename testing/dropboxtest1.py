# Include the Dropbox SDK
import dropbox
from pprint import pprint

# Get your app key and secret from the Dropbox developer website
app_key = 'pk2y4rsbrubnzwe'
app_secret = 'u969b7hxv5jz83e'

flow = dropbox.client.DropboxOAuth2FlowNoRedirect(app_key, app_secret)

# Have the user sign in and authorize this token
#authorize_url = flow.start()
#print '1. Go to: ' + authorize_url
#print '2. Click "Allow" (you might have to log in first)'
#print '3. Copy the authorization code.'
#code = raw_input("Enter the authorization code here: ").strip()
#print 'Code is: ', code

# This will fail if the user enters an invalid authorization code
#access_token, user_id = flow.finish(code)
#print 'access_token: ', access_token

access_token = 'yd0PQdjPz0sAAAAAAAAAAWoWEA1yPLVJ5BfBy4I9NKta-yJrb-UJPPtXeh4Emkgt'
client = dropbox.client.DropboxClient(access_token)
print 'linked account: ', client.account_info()

f = open('working-draft.txt', 'rb')
response = client.put_file('/magnum-opus.txt', f)
print 'uploaded: ', response

folder_metadata = client.metadata('/')
print 'metadata: ', folder_metadata

f, metadata = client.get_file_and_metadata('/magnum-opus.txt')
out = open('magnum-opus.txt', 'wb')
out.write(f.read())
out.close()
pprint(metadata)
