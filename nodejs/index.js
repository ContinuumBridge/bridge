
require('./env');

var BridgeConcentrator = require('./bridge/bridge_socket.js')
    ,ControllerSocket = require('./controller/controller_socket.js')
    ,controllerAuth = require('./controller/controller_auth.js')
    ,Heartbeat = require('./heartbeat.js')
    ;

var logger = require('./logger');

/* Node concentrator for managing socket communication between Bridge Manager and the main server (Controller) */

var bridgeConcentrator = new BridgeConcentrator(5000);

var controllerSocket = new ControllerSocket();

var heartbeat = new Heartbeat(controllerSocket, bridgeConcentrator);
heartbeat.start();

controllerSocket.fromController.onValue(function(message) {

    // Take messages from the controller and relay them to the bridge
    bridgeConcentrator.toBridge.push(message);
    logger.info('Controller => Bridge: ', message)
});

bridgeConcentrator.fromBridge.onValue(function(message) {

    // Take messages from the bridge and relay them to the controller
    controllerSocket.toController.push(message);
    logger.info('Bridge => Controller: ', message);
});

connectToController = function() {

    controllerAuth(CONTROLLER_API, BRIDGE_EMAIL, BRIDGE_PASSWORD).then(function(sessionID) {

        logger.info('Authenticated to Bridge Controller');

        controllerSocket.connect(CONTROLLER_SOCKET, sessionID);

        /* TODO {"msg":"aggregator_status", "data":"ok"} */
    }, function(error) {

        logger.error(error);
        logger.info('Retrying..');
        // Authorise again after 8 seconds
        setTimeout(connectToController, 8000);
    });
};

connectToController();

// Restart connection process on 'giveUp'
controllerSocket.on('giveUp', function() {
    logger.log('debug', 'calling connectToController after giveUp');
    connectToController();
});

