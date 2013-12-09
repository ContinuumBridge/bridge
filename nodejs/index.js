
// Get the arguments passed to node

var CONTROLLER_ADDRESS = (process.argv[2]) ? process.argv[2] : 'http://54.200.16.244:8000/api/v1/';
var BRIDGE_EMAIL = (process.argv[3]) ? process.argv[3] : '3b84fb342d3644b2a6a0f342311fc8e2@continuumbridge.com';
var BRIDGE_PASSWORD = (process.argv[4]) ? process.argv[4] : 'BEjEu+vAXP4k8Y1qySPdCrN8VrQ5OxewtLfDs58VnIA5VufYahF/QndOSH4cqN7u';

console.log('CONTROLLER_ADDRESS', CONTROLLER_ADDRESS);
console.log('BRIDGE_EMAIL', BRIDGE_EMAIL);
console.log('BRIDGE_PASSWORD', BRIDGE_PASSWORD);

var BridgeConcentrator = require('./bridge/bridge_concentrator.js');
bridgeConcentrator = new BridgeConcentrator(5000);

var controllerAuth = require('./controller/controller_auth.js');

//var BRIDGE_EMAIL = '3b84fb342d3644b2a6a0f342311fc8e2@continuumbridge.com';
//var BRIDGE_PASSWORD = 'BEjEu+vAXP4k8Y1qySPdCrN8VrQ5OxewtLfDs58VnIA5VufYahF/QndOSH4cqN7u'

controllerAuth(CONTROLLER_ADDRESS, BRIDGE_EMAIL, BRIDGE_PASSWORD).then(function(sessionID) {

    console.log('controllerAuth returned', sessionID);

    var ControllerSocket = require('./controller/controller_socket.js');
    controllerSocket = new ControllerSocket('http://54.200.16.244:3000/', sessionID);

    controllerSocket.fromController.onValue(function(message) {

        // Take messages from the controller and relay them to the bridge 
        console.log('Controller >', message);
        bridgeConcentrator.toBridge.push(message);
        //var cmdJSON = JSON.stringify(cmd);
        //bridgeConcentrator.socket.write(cmdJSON + '\r\n');
    });

    bridgeConcentrator.fromBridge.onValue(function(message) {
        
        // Take messages from the bridge and relay them to the controller
        console.log('Bridge >', message);
        controllerSocket.toController.push(message);
    });

    /*
    setTimeout(function sendMessage() {
        console.log('Sending message!');
        controllerSocket.toController.push('Test message!');
        setTimeout(sendMessage, 2000);
    }, 6000);
    */

}, function(error) {
    console.log('controllerAuth returned error', error);
});

