from twisted.internet import reactor, defer
from .socket_io import SocketThread, SocketCommand, SocketReply

class SocketThreadWrapper(object):

    unused_ids = []
    highest_id = 0
    deferred_requests = {}

    def __init__(self, *args, **kwargs):
        self.socket = SocketThread(*args, **kwargs)

    def get_unused_id(self):
        try:
            return self.unused_ids.pop()
        except IndexError:
            self.highest_id += 1
            return self.highest_id

    def create_request(self, type, data):

        deferred = defer.Deferred()
        self.deferred_requests[self.get_unused_id()] = deferred

    def send(self, message):
        pass

    def close(self):
        pass

    def handle_reply(self, reply):
        try:
            deferred = self.deferred_requests[reply.id]
        except AttributeError:
            # The reply has no id
        except KeyError:





