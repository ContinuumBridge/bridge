// Set up the socket client
var io = require('socket.io-client'),
wSocket = io.connect('54.200.16.244', {
    port: 4000 
});
wSocket.on('connect', function () { console.log("Web socket connected"); });
wSocket.emit('status', { status: 'ready' });

// Set up the TCP socket for the bridge
var net = require('net');
var BRIDGE_HOST = '127.0.0.1';
var BRIDGE_PORT = 5000;

var bridgeTCPClient = new net.Socket();
bridgeTCPClient.connect(PORT, HOST, function() {

    console.log('Local TCP socket connected on: ' + HOST + ':' + PORT);
    bridgeTCPClient.write('Hi from node!');
});

bridgeTCPClient.on('data', function(data) {
    
    console.log('DATA: ' + data);
    wSocket.emit('data', data);
});

// Add a 'close' event handler for the bridgeTCPClient socket
bridgeTCPClient.on('close', function() {
    console.log('Bridge connection closed');
});

/*
var dgram = require('unix-dgram');
// Create unix socket
uSocket = dgram.createSocket('unix_dgram', 'listener');
//uSocket.bind(fdesc); 
var message = new Buffer("Test message");
uSocket.send(message, 0, message.length, '/tmp/testSoc.sock' , function(err, bytes) {
    console.log('Error connecting:', err, bytes);
});

/*
// Imports for unix socket
var net = require('net'),
    fs = require('fs'),
    uSocket;

// Create socket file
fs.open('/tmp/testSoc.sock', 'w+', function(err, fdesc){

    if (err || !fdesc) {
        throw 'Error: ' + (err || 'No fdesc');
    }

    console.log(fdesc);

    // Create socket
    //uSocket = net.connect('/tmp/testSoc.sock');
    uSocket = new net.Socket({ fd : fdesc,
                               type: 'unix', 
                            });

    uSocket.on('connect', function () { console.log("Unix socket connected"); });
    console.log(uSocket);
    
    uSocket.write("test");
});
*/
