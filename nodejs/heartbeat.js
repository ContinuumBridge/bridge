
var Message = require('./message');



var Heartbeat = function(controllerSocket, bridgeSocket) {

    /* Periodically sends a message to the bridge manager with connection status */

    var heartbeat = {};
    heartbeat.controllerSocket = controllerSocket;
    heartbeat.bridgeSocket = bridgeSocket;

    heartbeat.start = function() {

        var message = new Message({message: "status", source: "conduit"})

        setInterval(function() {

            message.set('body',{connected: controllerSocket.connected});
            bridgeSocket.toBridge.push(message);
        }, 1000);
    }
    return heartbeat;
}

module.exports = Heartbeat;
