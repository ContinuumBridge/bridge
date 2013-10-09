
var SERVER_PORT = 3000;
// Set up the socket client
var io = require('socket.io-client');
var Bacon = require('baconjs').Bacon;

/* Controller Web Socket */

module.exports = ControllerSocket;

function ControllerSocket(ip, port) {

    var controllerSocket = {};

    var socket = io.connect(ip, {
        port: port 
    });

    socket.on('connect', function() { 

        //var address = socket.handshake.address;
        console.log('Server > Connected to Bridge Controller');
        // + address.address + ":" + address.port);
        //controllerSocket.emit('status', { status: 'ready' }); 
    });

    var commands = new Bacon.Bus();

    socket.on('message', function(cmd) {

        console.log('Controller > ' + cmd);
        commands.push(cmd);
    });

    socket.on('diconnect', function() {

        console.log('Server > Disconnected from Bridge Controller');
    }); 

    controllerSocket.socket = socket;
    controllerSocket.commands = commands;

    return controllerSocket;
}
