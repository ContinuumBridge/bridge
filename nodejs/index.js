
// Get the arguments passed to node

var CONTROLLER_IP = (process.argv[2]) ? process.argv[2] : '54.194.28.63';
var CONTROLLER_API = 'http://' + CONTROLLER_IP + ':8000/api/v1/';
var CONTROLLER_SOCKET = 'http://' + CONTROLLER_IP + ':3000/';
var BRIDGE_EMAIL = (process.argv[3]) ? process.argv[3] : '28b45a59a875478ebcbdf327c18dbfb1@continuumbridge.com';
var BRIDGE_PASSWORD = (process.argv[4]) ? process.argv[4] : 'oX3ZGWS/yY1l+PaEFsBp11yixvK6b7O5UiK9M9TV8YBnjPXl3bDLw9eXQZvpmNdr';

console.log('CONTROLLER_API', CONTROLLER_API);
console.log('BRIDGE_EMAIL', BRIDGE_EMAIL);
console.log('BRIDGE_PASSWORD', BRIDGE_PASSWORD);

var BridgeConcentrator = require('./bridge/bridge_concentrator.js');
var bridgeConcentrator = new BridgeConcentrator(5000);

var controllerAuth = require('./controller/controller_auth.js');

controllerAuth(CONTROLLER_API, BRIDGE_EMAIL, BRIDGE_PASSWORD).then(function(sessionID) {

    console.log('SessionID:', sessionID);

    var ControllerSocket = require('./controller/controller_socket.js');
    controllerSocket = new ControllerSocket(CONTROLLER_SOCKET, sessionID);

    controllerSocket.fromController.onValue(function(message) {

        // Take messages from the controller and relay them to the bridge 
        console.log('Controller >', message);
        bridgeConcentrator.toBridge.push(message);
        //var cmdJSON = JSON.stringify(cmd);
        //bridgeConcentrator.socket.write(cmdJSON + '\r\n');
    });

    /* TODO {"msg":"aggregator_status", "data":"ok"} */

    bridgeConcentrator.fromBridge.onValue(function(jsonMessage) {
        
        // Take messages from the bridge and relay them to the controller
        console.log('Bridge >', jsonMessage);

        message = JSON.parse(jsonMessage);

        console.log('Bridge >', message.msg);

        if (message.msg == 'req') {
            if (message.uri == '/api/v1/current_bridge/bridge') {
                
                //console.log('Bridge Config >', message);
                var resp = {};
                resp.msg = 'cmd';
                resp.uri = '/api/v1/current_bridge/bridge';
                resp.data = 'Test data';
                bridgeConcentrator.toBridge.push(JSON.stringify(resp));
            }
        }
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

