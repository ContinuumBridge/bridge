"""
Simple web server test
"""

from pprint import pprint
from twisted.application.internet import TCPServer
from twisted.application.service import Application
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet import reactor
import json

class AccelPage(Resource):
    isLeaf = True
    def render_GET(self, request):
        print "Accel GET:"
        pprint(request.__dict__)
        newdata = request.content.getvalue()
        print "newdata:"
        response = {"resp": "data",
                    "data": "response to Accel GET"}
        return json.dumps(response) 

    def render_POST(self, request):
        print "Accel POST:"
        pprint(request.__dict__)
        newdata = request.content.getvalue()
        print "newdata:"
        print newdata
        req = json.loads(newdata)
        if req["req"] == "one":
            response = {"resp": "data",
                        "data": "first accel POST"}
        else:
            response = {"resp": "data",
                        "data": "second accel POST"}
        return json.dumps(response) 

class TempPage(Resource):
    isLeaf = True
    def render_GET(self, request):
        print "Temp GET:"
        pprint(request.__dict__)
        newdata = request.content.getvalue()
        print "newdata:"
        response = {"resp": "data",
                    "data": "response to Temp GET"}
        return json.dumps(response) 

    def render_POST(self, request):
        print "Temp POST:"
        pprint(request.__dict__)
        newdata = request.content.getvalue()
        print "newdata:"
        print newdata
        req = json.loads(newdata)
        if req["req"] == "one":
            response = {"resp": "data",
                        "data": "first temp POST"}
        else:
            response = {"resp": "data",
                        "data": "second temp POST"}
        return json.dumps(response) 

class BridgePage(Resource):
    isLeaf = False
    def getChild(self, name, request):
        if name == "accel":
            return AccelPage()
        elif name == "temp":
            return TempPage()

root = Resource()
root.putChild("bridge", BridgePage())
application = Application("Bridge Web Service")
factory = Site(root)
reactor.listenTCP(8880, factory)
reactor.run()

