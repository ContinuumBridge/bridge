
var getenv = require('getenv');
var winston = require('winston');

winston.log('info', 'Test log from winston');

var BridgeConcentrator = require('./bridge/bridge_concentrator.js');
var bridgeConcentrator = new BridgeConcentrator(5000);

var controllerAuth = require('./controller/controller_auth.js');
var ControllerSocket = require('./controller/controller_socket.js');

// Get some values from the environment
var CONTROLLER_API = "http://" + getenv('CB_DJANGO_CONTROLLER_ADDR') + "/api/v1/";
console.log('CONTROLLER_API', CONTROLLER_API);
var CONTROLLER_SOCKET = "http://" + getenv('CB_NODE_CONTROLLER_ADDR') + "/"; 
console.log('CONTROLLER_SOCKET', CONTROLLER_SOCKET);
var BRIDGE_EMAIL = getenv('CB_BRIDGE_EMAIL', '28b45a59a875478ebcbdf327c18dbfb1@continuumbridge.com');
console.log('BRIDGE_EMAIL', BRIDGE_EMAIL);
var BRIDGE_PASSWORD = getenv('CB_BRIDGE_PASSWORD', 'oX3ZGWS/yY1l+PaEFsBp11yixvK6b7O5UiK9M9TV8YBnjPXl3bDLw9eXQZvpmNdr');
console.log('BRIDGE_PASSWORD', BRIDGE_PASSWORD);

controllerAuth(CONTROLLER_API, BRIDGE_EMAIL, BRIDGE_PASSWORD).then(function(sessionID) {

    console.log('SessionID:', sessionID);

    controllerSocket = new ControllerSocket(CONTROLLER_SOCKET, sessionID);

    controllerSocket.fromController.onValue(function(message) {

        // Take messages from the controller and relay them to the bridge 
        console.log('Controller >', message);
        bridgeConcentrator.toBridge.push(message);

        var testMessage = {};
        testMessage.message = "wrapper";
        testMessage.channel = "APPID1";
        testMessage.body = "Test temperature reading";
        //testMessage.verb = "get";
        //testMessage.url = "api/v1/current_bridge/bridge";
        
        controllerSocket.toController.push(JSON.stringify(testMessage));
    });

    /* TODO {"msg":"aggregator_status", "data":"ok"} */

    bridgeConcentrator.fromBridge.onValue(function(jsonMessage) {
        
        // Take messages from the bridge and relay them to the controller
        console.log('Bridge >', jsonMessage);

        var message = JSON.parse(jsonMessage);

        //console.log('Bridge >', message.msg);

        /*
        if (message.msg == 'req') {
            if (message.uri == '/api/v1/current_bridge/bridge') {
                
                //console.log('Bridge Config >', message);
                fs = require('fs')
                fs.readFile('./test_config.json', 'utf8', function (err, test_config) {
                    if (err) {
                        return console.log(err);
                    }
                    resp = {};
                    resp.msg = "resp";
                    resp.body = JSON.parse(test_config);
                    bridgeConcentrator.toBridge.push(JSON.stringify(resp));
                });
            }
        }
        */
        controllerSocket.toController.push(jsonMessage);
        var msg = {};
        msg.message = 'request';
        msg.body = 'request';
        controllerSocket.toController.push(JSON.stringify(msg));
    });

    /*
    setTimeout(function sendMessage() {
        console.log('Sending message!');
        var msg = {};
        msg.message = 'request';
        msg.body = 'request';
        //msg.uri = '/api/v1/device_discovery';
        controllerSocket.toController.push(JSON.stringify(msg));
        setTimeout(sendMessage, 6000);
    }, 6000);
    */

}, function(error) {
    console.log('controllerAuth returned error', error);
});

