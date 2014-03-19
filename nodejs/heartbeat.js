
var Q = require('q');

var Heartbeat = function(controllerSocket, bridgeSocket) {

    /* Periodically sends a message to the bridge manager with connection status */

    var heartbeat = {};
    heartbeat.controllerSocket = controllerSocket;
    heartbeat.bridgeSocket = bridgeSocket;

    heartbeat.start = function() {

        var message = {};
        message.message = "status";
        message.source = "conduit";

        setInterval(function() {

            message.body = '{"connected":"' + controllerSocket.connected + '"}';
            bridgeSocket.toBridge.push(message);
        }, 1000);
    }
    return heartbeat;
}

module.exports = Heartbeat;
