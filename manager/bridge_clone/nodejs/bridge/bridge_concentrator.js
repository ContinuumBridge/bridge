
// Set up the TCP socket for the bridge
var net = require('net');
var Bacon = require('baconjs').Bacon;

module.exports = BridgeConcentrator;

function BridgeConcentrator(port) {

    var bridgeConcentrator = {};

    var fromBridge = new Bacon.Bus();
    var toBridge = new Bacon.Bus();

    bridgeConcentrator.bridgeServer = net.createServer(function(socket) {

        socket.setEncoding('utf8');

        console.log('Concentrator > Connected to Bridge');

        toBridge.onValue(function(message) {

            console.log('Writing to bridge', message);
            socket.write(message + '\r\n');
        });

        socket.on('data', function(data) {

            console.log('Raw data', data);
            fromBridge.push(data);
        }); 

        // Add a 'close' event handler for the bridgeTCPClient socket
        socket.on('close', function() {

            console.log('Server > Bridge connection closed');
        }); 

        bridgeConcentrator.socket = socket;
    });

    bridgeConcentrator.bridgeServer.listen(port, function() {
        console.log('Server > Listening on port ', port);
    });

    bridgeConcentrator.fromBridge = fromBridge;
    bridgeConcentrator.toBridge = toBridge;

    return bridgeConcentrator;
}

