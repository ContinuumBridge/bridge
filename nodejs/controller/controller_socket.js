
var SERVER_PORT = 3000;
// Set up the socket client
var io = require('socket.io-client')
    ,Bacon = require('baconjs').Bacon
    ,events = require('events');
    ;

var logger = require('../logger')
    ,Message = require('../message')
    ;

/* Controller socket manager */

module.exports = ControllerSocket;

function ControllerSocket(controllerURL, sessionID) {

    var socketWrapper = new events.EventEmitter();

    // Connection status flag
    socketWrapper.connected = false;

    var fromController = socketWrapper.fromController = new Bacon.Bus();
    var toController = socketWrapper.toController = new Bacon.Bus();

    socketWrapper.on('connect', function() {

        socketWrapper.clearConnectionTimeout();

        socketWrapper.unsubscribeControllerBus = toController.onValue(function(message) {

            var jsonMessage = message.getJSON();
            if (socketWrapper.socket) {
                socketWrapper.socket.emit('message', jsonMessage);
            } else {
                logger.error('socket connect fired but there is no socket?');
            }
        });
        socketWrapper.connected = true;

        socketWrapper.socket.on('message', function(jsonMessage) {

            var message = new Message(jsonMessage);
            // When the socket receives a message push it to the fromController bus
            fromController.push(message);
        });

        logger.info('Connected to Bridge Controller:', socketWrapper.controllerURL);
    });

    socketWrapper.startConnectionTimeout = function() {

        socketWrapper.clearConnectionTimeout();

        // Set a timeout to start re-authorisation if connection is not established
        socketWrapper.connectionTimeout = setTimeout(function() {
            logger.log('debug', 'connect timed out');
            socketWrapper.giveUp();
        }, 10000);
    };

    socketWrapper.clearConnectionTimeout = function() {

        // If there is an existing timeout, clear it
        if (socketWrapper.connectionTimeout) {
            clearTimeout(socketWrapper.connectionTimeout);
            logger.log('debug', 'connectTimeout cleared');
        }
    };

    socketWrapper.giveUp = function() {

        logger.log('debug', 'giveUp');
        socketWrapper.emit('disconnect');
        //logger.log('debug', 'In giveUp socketWrapper.socket is', socketWrapper.socket.co);
        if (socketWrapper.socket) {
            var socket = socketWrapper.socket;
            socket.removeAllListeners();
            socket.disconnect();
            delete socket;
        }
        socketWrapper.emit('giveUp');
    };

    // Socket Wrapper listeners
    socketWrapper.on('connecting', function() {

        logger.info('Connecting..');
    });

    socketWrapper.on('disconnect', function() {

        socketWrapper.connected = false;
        if (socketWrapper.unsubscribeControllerBus) {
            socketWrapper.unsubscribeControllerBus();
        };
        logger.info('Disconnected from Bridge Controller:', controllerURL);
        socketWrapper.startConnectionTimeout();
    });

    socketWrapper.connect = function(controllerURL, sessionID) {

        socketWrapper.controllerURL = controllerURL;
        var socketAddress = controllerURL + "?sessionID=" + sessionID;
        var socket = socketWrapper.socket = io.connect(socketAddress, {
            //'max reconnection attempts': 10,
            'force new connection': true,
            //'auto connect': false,
            'log level': 2,
            'reconnect': false
        });

        // Proxy socket events to the controllerSocketWrapper
        socket.on('connect', function() {
            logger.log('debug', 'socket connect', controllerURL);
            socketWrapper.emit('connect');
        });
        socket.on('connecting', function() {
            logger.log('debug', 'socket connecting', controllerURL);
            socketWrapper.emit('connecting');
        });
        socket.on('error', function() {
            logger.log('debug', 'socket error', controllerURL);
            socketWrapper.giveUp();
        });
        socket.on('reconnecting', function() {
            logger.log('debug', 'socket reconnecting', controllerURL);
            socketWrapper.emit('connecting');
        });
        socket.on('reconnect', function() {
            logger.log('debug', 'socket reconnect', controllerURL);
            socketWrapper.emit('connect');
        });
        socket.on('disconnect', function() {
            logger.log('debug', 'socket disconnect', controllerURL);
            socketWrapper.emit('disconnect');
        });

        logger.info('Establishing socket to Bridge Controller:', controllerURL);

        // Run on initial attempt to connect
        socketWrapper.startConnectionTimeout();
    };

    return socketWrapper;
}
