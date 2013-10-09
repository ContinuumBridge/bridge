
// Set up the TCP socket for the bridge
var net = require('net');
    JsonSocket = require('json-socket');
//var BRIDGE_PORT = 5000;
var Bacon = require('baconjs').Bacon;
//var bridgeSocket;

module.exports = BridgeConcentrator;

function BridgeConcentrator(port) {

    var bridgeConcentrator = {};

    bridgeConcentrator.messages = new Bacon.Bus();

    bridgeConcentrator.bridgeServer = net.createServer(function(socket) {

        socket.on('connect', function() {

            //var address = socket.handshake.address;
            console.log('Server > New bridge connection');
            // + address.address + ":" + address.port);
            //socket.write('test\r\n');
        }); 

        socket.on('data', function(data) {

            bridgeConcentrator.messages.push(data);
        }); 
            
        // Add a 'close' event handler for the bridgeTCPClient socket
        socket.on('close', function() {

            //var address = socket.handshake.address;
            console.log('Server > Bridge connection closed');
            // from ' + address.address + ":" + address.port);
        }); 

        bridgeConcentrator.socket = socket;
    });

    bridgeConcentrator.bridgeServer.listen(port, function() {
        console.log('Server > Listening on port ', port);
    });

    return bridgeConcentrator;
}

