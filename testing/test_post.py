import httplib2
from datetime import datetime
import json


TESTDATA = {'woggle': {'version': 1234,
                       'updated': str(datetime.now()),
                       }}
URL = 'http://localhost:8880/bridge/accel'
req = {"req": "one"}
jsondata = json.dumps(req)
h = httplib2.Http()
resp, content = h.request(URL,
                          'POST',
                          jsondata,
                          headers={'Content-Type': 'application/json'})
print resp
print content
print ""
print ""
req = {"req": "two"}
jsondata = json.dumps(req)
h = httplib2.Http()
resp, content = h.request(URL,
                          'POST',
                          jsondata,
                          headers={'Content-Type': 'application/json'})
print resp
print content
print ""
print ""
URL = 'http://localhost:8880/bridge/accel'
h = httplib2.Http()
resp, content = h.request(URL,
                          'GET')
print resp
print content
print ""
print ""

URL = 'http://localhost:8880/bridge/temp'
h = httplib2.Http()
resp, content = h.request(URL,
                          'GET')
print resp
print content
print ""
print ""

