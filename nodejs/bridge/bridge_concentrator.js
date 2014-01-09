
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

        socket.on('connect', function() {

            console.log('Server > Connected to Bridge');

            toBridge.onValue(function(message) {

                //var messageJSON = JSON.stringify(message);
                console.log('Writing to bridge', message);
                //console.log('Writing JSON to bridge', messageJSON);
                socket.write(message + '\r\n');
            });
        }); 

        socket.on('data', function(data) {

            //console.log('Raw data', data);
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

