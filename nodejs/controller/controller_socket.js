
var SERVER_PORT = 3000;
// Set up the socket client
var io = require('socket.io-client');
var Bacon = require('baconjs').Bacon;

/* Controller Web Socket */

module.exports = ControllerSocket;

function ControllerSocket(controllerURL, sessionID) {

    var controllerSocket = {};

    var socketAddress = controllerURL + '?sessionID=' + sessionID;
    var socket = io.connect(socketAddress);

    var fromController = new Bacon.Bus();
    var toController = new Bacon.Bus();

    socket.on('connect', function() { 

        console.log('Server > Connected to Bridge Controller');

        toController.onValue(function(message) {
            socket.emit('message', message); 
        });
    });

    socket.on('message', function(message) {

        //console.log('Controller > ' + message);
        fromController.push(message);
    });

    socket.on('disconnect', function() {

        console.log('Server > Disconnected from Bridge Controller');
    }); 

    controllerSocket.socket = socket;
    controllerSocket.fromController = fromController;
    controllerSocket.toController = toController;

    return controllerSocket;
}
