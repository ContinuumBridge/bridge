
import json
import struct
import threading
import Queue
import requests
from socketIO_client import SocketIO, LoggingNamespace

from .conf import CB_ADDRESS, KEY, AUTH_PORT, SOCKET_PORT, BRIDGE_AUTH_SUFFIX \
    , BRIDGE_SOCKET_SUFFIX, CLIENT_AUTH_SUFFIX, CLIENT_SOCKET_SUFFIX

class SocketCommand(object):
    """ A command to the client thread.
        Each command type has its associated data:

        CONNECT:    (host, port) tuple
        SEND:       Data string
        RECEIVE:    None
        CLOSE:      None
    """
    CONNECT, SEND, RECEIVE, CLOSE = range(4)

    def __init__(self, type, data=None):
        self.type = type
        self.data = data


class SocketReply(object):
    """ A reply from the client thread.
        Each reply type has its associated data:

        ERROR:      The error string
        SUCCESS:    Depends on the command - for RECEIVE it's the received
                    data string, for others None.
    """
    CONNECTED, DISCONNECTED, MESSAGE, ERROR, SUCCESS = range(5)

    def __init__(self, type, data=None):
        self.type = type
        self.data = data


class SocketThread(threading.Thread):
    """ Implements the threading.Thread interface (start, join, etc.) and
        can be controlled via the cmd_q Queue attribute. Replies are
        placed in the reply_q Queue attribute.
    """
    def __init__(self, is_bridge=False, cmd_q=None, reply_q=None):
        print "CBClientThread init"
        super(SocketThread, self).__init__()
        self.cmd_q = cmd_q or Queue.Queue()
        self.reply_q = reply_q or Queue.Queue()
        self.alive = threading.Event()
        self.alive.set()

        self.auth_url = "https://" + CB_ADDRESS \
                            + (BRIDGE_AUTH_SUFFIX if is_bridge else CLIENT_AUTH_SUFFIX)
        self.socket_url = "https://" + CB_ADDRESS \
                            + (BRIDGE_SOCKET_SUFFIX if is_bridge else CLIENT_SOCKET_SUFFIX)
        self.socket_port = 443

        self.session_id = ""
        self.socket = None

        self.handlers = {
            #ClientCommand.CONNECT: self._handle_CONNECT,
            SocketCommand.CLOSE: self._handle_CLOSE,
            SocketCommand.SEND: self._handle_SEND,
#           ClientCommand.RECEIVE: self._handle_RECEIVE,
        }

    def run(self):
        print "CBClientThread run"
        print "self.alive.isSet() is", self.alive.isSet()
        while self.alive.isSet():
            print "while self.alive.isSet() is", self.alive.isSet()
            if not self.session_id:
                self.authorise()
                self.connect()

            try:
                # Queue.get with timeout to allow checking self.alive
                cmd = self.cmd_q.get(True, 0.5)
                self.handlers[cmd.type](cmd)
            except Queue.Empty as e:
                continue

            self.socket.wait(seconds=0.5)

    def join(self, timeout=None):
        self.alive.clear()
        threading.Thread.join(self, timeout)

    def authorise(self):

        self.session_id = ""
        print "authorise"
        print "self.auth_url is", self.auth_url
        auth_data = '{"key": "' + KEY + '"}'
        auth_headers = {'content-type': 'application/json'}
        response = requests.post(self.auth_url, data=auth_data, headers=auth_headers)
        print "response.text is", response.text
        #self.cbid = json.loads(response.text)['cbid']
        self.session_id = response.cookies.get('sessionid', "")

    def connect(self):

        print "socket connect"
        self.socket = SocketIO(self.socket_url, SOCKET_PORT
                               , LoggingNamespace
                               , cookies={'sessionid': self.session_id})

        self.socket.on('connect', self.on_connect)
        self.socket.on('reconnect', self.on_connect)
        self.socket.on('message', self.on_message)
        self.socket.on('error', self.on_socket_error)
        self.socket.on('reconnect_error', self.on_socket_error)
        self.socket.on('reconnect_failed', self.on_socket_failed)
        self.socket.on('disconnect', self.on_disconnect)

        reply = SocketReply(SocketReply.CONNECTED)
        self.reply_q.put(reply)
        print "socket connected"

    def destroy_socket(self):
        self.socket.disconnect()
        self.socket = None

    # Event listeners for the socket
    def on_connect(self):
        print "Socket connected"
        reply = SocketReply(SocketReply.CONNECTED)
        self.reply_q.put(reply)

    def on_message(self, message):
        print "Socket got message" + message
        self.reply_q.put(self._success_reply(message))

    def on_disconnect(self, message):
        print "Socket disconnected"
        reply = SocketReply(SocketReply.DISCONNECTED)
        self.reply_q.put(reply)

    def on_socket_error(self, error):
        print "Socket error " + error
        #reply = ClientReply(ClientReply.CONNECTED)
        #self.reply_q.put(reply)

    def on_socket_failed(self, error):
        print "Socket failed " + error
        self.session_id = ""
        self.destroySocket()

    @property
    def connected(self):
        try:
            return self.socket._opened
        except AttributeError as e:
            return False

        '''
        try:
            self.socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((cmd.data[0], cmd.data[1]))
            self.reply_q.put(self._success_reply())
        except IOError as e:
            self.reply_q.put(self._error_reply(str(e)))
        '''

    # Methods to handle commands from the application thread
    def _handle_CLOSE(self, cmd):
        print "_handle_CLOSE "
        self.destroySocket()
        self._success_reply()

    def _handle_SEND(self, cmd):
        print "_handle_SEND message ", cmd.data
        if not self.connected:
            self.reply_q.put(self._error_reply("Socket not connected"))
        else:
            self.socket.emit('message', cmd.data)

        '''
        header = struct.pack('<L', len(cmd.data))
        try:
            self.socket.sendall(header + cmd.data)
            self.reply_q.put(self._success_reply())
        except IOError as e:
            self.reply_q.put(self._error_reply(str(e)))
        '''

    def _message_reply(self, data=None):
        return SocketReply(SocketReply.MESSAGE, data)

    def _error_reply(self, errstr):
        return SocketReply(SocketReply.ERROR, errstr)

    def _success_reply(self, data=None):
        return SocketReply(SocketReply.SUCCESS, data)

    '''
    def _handle_RECEIVE(self, cmd):

        try:
            header_data = self._recv_n_bytes(4)
            if len(header_data) == 4:
                msg_len = struct.unpack('<L', header_data)[0]
                data = self._recv_n_bytes(msg_len)
                if len(data) == msg_len:
                    self.reply_q.put(self._success_reply(data))
                    return
            self.reply_q.put(self._error_reply('Socket closed prematurely'))
        except IOError as e:
            self.reply_q.put(self._error_reply(str(e)))

    def _recv_n_bytes(self, n):
        """ Convenience method for receiving exactly n bytes from
            self.socket (assuming it's open and connected).
        """
        data = ''
        while len(data) < n:
            chunk = self.socket.recv(n - len(data))
            if chunk == '':
                break
            data += chunk
        return data
    '''

