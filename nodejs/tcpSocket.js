
// Set up the TCP socket for the bridge
var net = require('net')
    ,util = require('util')
    ;

var CB = require('./index');

/* TCP socket manager */

function TCPSocket(port) {

    var self = this;

    this.server = net.createServer(function(socket) {

        socket.setEncoding('utf8');

        socket.on('data', function(jsonMessage) {

            console.log('data is', jsonMessage);
            var message = new Message(jsonMessage);
            self.emit('message', message);
        });

        // Add a 'close' event handler for the TCPClient socket
        socket.on('close', function() {

            socket.removeListener('data');
            self.removeListener('message');
            logger.info('TCP socket disconnected');
        });

        self.socket = socket;

        logger.info('TCP socket connected');

    }).listen(port);
}

var EventEmitter = require('events').EventEmitter;
util.inherits(TCPSocket, EventEmitter);

TCPSocket.prototype.publish = function(message) {

    var jsonMessage = message instanceof Message ? message.toJSONString() : message;
    if (this.socket) this.socket.write(jsonMessage + '\r\n');
}

module.exports = TCPSocket;

