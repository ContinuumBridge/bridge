import httplib2
from datetime import datetime
import json

config = {"dev1": ["temp", "accel"]}
configData = json.dumps(config)
URL = 'http://localhost:8880/config'
h = httplib2.Http()
resp, content = h.request(URL,
                          'POST',
                          configData,
                          headers={'Content-Type': 'application/json'})
print resp
print content
print ""
print ""

UURL = 'http://localhost:8880/config'
h = httplib2.Http()
resp, content = h.request(URL,
                          'GET',
                          headers={'Content-Type': 'application/json'})
print resp
print content
print ""
print ""

UURL = 'http://localhost:8880/config'
h = httplib2.Http()
resp, content = h.request(URL,
                          'DELETE',
                          headers={'Content-Type': 'application/json'})
print resp
print content
print ""
print ""

URL = 'http://localhost:8880/device/dev1'
h = httplib2.Http()
resp, content = h.request(URL,
                          'GET',
                          headers={'Content-Type': 'application/json'})
print resp
print content
print ""
print ""

URL = 'http://localhost:8880/device/dev2'
h = httplib2.Http()
resp, content = h.request(URL,
                          'GET',
                          headers={'Content-Type': 'application/json'})
print resp
print content
print ""
print ""

