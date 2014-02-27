
var SERVER_PORT = 3000;
// Set up the socket client
var io = require('socket.io-client');
var Bacon = require('baconjs').Bacon;
    Q = require('q');

/* Controller Web Socket */

module.exports = ControllerSocket;

function ControllerSocket(controllerURL, sessionID) {

    console.log('Attempting to connect to', controllerURL);
    var controllerSocket = {};
    controllerSocket.connected = false;

    var socketAddress = controllerURL + "?sessionID=" + sessionID;
    var socket = io.connect(socketAddress);

    var fromController = new Bacon.Bus();
    var toController = new Bacon.Bus();
    var unsubscribeControllerSocket = function(){};

    socket.on('connect', function() { 

        controllerSocket.connected = true;

        unsubscribeControllerSocket = toController.onValue(function(message) {
            socket.emit('message', message); 
        });
        console.log('Server > Connected to Bridge Controller');
    });

    socket.on('message', function(message) {

        //console.log('Controller > ' + message);
        fromController.push(message);
    });

    socket.on('disconnect', function() {

        controllerSocket.connected = false;
        unsubscribeControllerSocket();
        console.log('Server > Disconnected from Bridge Controller');
    }); 

    controllerSocket.socket = socket;
    controllerSocket.fromController = fromController;
    controllerSocket.toController = toController;

    return controllerSocket;
}
