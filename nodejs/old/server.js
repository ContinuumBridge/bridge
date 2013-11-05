// Set up the socket client
var io = require('socket.io-client'),
serverSocket = io.connect('54.200.16.244', {
    port: 4000 
});
serverSocket.on('connect', function () { console.log("Web socket connected"); });
serverSocket.emit('status', { status: 'ready' });

// Set up the TCP socket for the bridge
var net = require('net');
var BRIDGE_PORT = 5000;
//var bridgeSocket;

net.createServer(function(bridgeSocket) {

    bridgeSocket.on('connect', function() {

        console.log('Local TCP socket connected on: ' + HOST + ':' + PORT);
        bridgeSocket.write('Hi from node!');
    });
    // Relay data from the TCP socket to the websocket
    bridgeSocket.on('data', function(data) {
        
        console.log('Data from bridge: ' + data);
        wSocket.emit('data', data);
    });
    
    // Add a 'close' event handler for the bridgeTCPClient socket
    bridgeSocket.on('close', function() {
        console.log('Bridge connection closed');
    });
});

serverSocket.on('cmd', function(cmd) {
    console.log('Command from server: ' + cmd);
    bridgeSocket.write('cmd', cmd);
});
