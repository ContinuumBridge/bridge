// Set up the socket client
var io = require('socket.io-client'),
socket = io.connect('54.200.16.244', {
    port: 4000 
});
socket.on('connect', function () { console.log("socket connected"); });
socket.emit('status', { status: 'ready' });

// Imports for unix socket
var net = require('net'),
    fs = require('fs'),
    sock;

// Create socket file
fs.open('/tmp/node.test.sock', 'w+', function(err, fdesc){

    if (err || !fdesc) {
        throw 'Error: ' + (err || 'No fdesc');
    }

    // Create socket
    sock = new net.Socket({ fd : fdesc });
    console.log(sock);
});


