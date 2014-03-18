
// Set up the TCP socket for the bridge
var net = require('net')
    ,Bacon = require('baconjs').Bacon
    ;

var logger = require('../logger')
    ,MessageUtils = require('../message_utils')
    ;

/* Bridge socket manager */

module.exports = BridgeConcentrator;

function BridgeConcentrator(port) {

    var bridgeConcentrator = {};
    // Connection status flag
    bridgeConcentrator.connected = false;

    var fromBridge = bridgeConcentrator.fromBridge =  new Bacon.Bus();
    var toBridge = bridgeConcentrator.toBridge = new Bacon.Bus();

    bridgeConcentrator.bridgeServer = net.createServer(function(socket) {

        socket.setEncoding('utf8');

        logger.info('Connected to Bridge Manager');

        toBridge.onValue(function(message) {

            var message = MessageUtils.stripFields(message);
            MessageUtils.stringify(message).then(function(jsonMessage) {
                if (message.source == 'conduit') {
                    logger.debug(message.source + ' => bridge', jsonMessage);
                } else {
                    logger.info(message.source + ' => bridge', jsonMessage);
                }
                socket.write(jsonMessage + '\r\n');
            }, function(error) {
                logger.error(error);
            });
        });

        socket.on('data', function(data) {

            fromBridge.push(data);
        }); 

        // Add a 'close' event handler for the bridgeTCPClient socket
        socket.on('close', function() {

            logger.info('Disconnected from Bridge Manager');
        }); 

        bridgeConcentrator.socket = socket;
    });

    bridgeConcentrator.bridgeServer.listen(port, function() {
        logger.info('Listening for Bridge Manager on port', port);
    });

    return bridgeConcentrator;
}

