
var winston = require('winston')
    ,path = require('path')
    ;

// Define thisBridgeRoot here so that we don't get circular dependencies loading ./env
var thisBridgeRoot = path.normalize(__dirname + '/../../thisbridge');

var logger = new (winston.Logger)({
  transports: [
    new (winston.transports.Console)({ json: false, timestamp: true, level: 'info' }),
    new winston.transports.File({ filename: thisBridgeRoot + "/node-debug.log", json: false, level: 'info' })
  ],
  exceptionHandlers: [
    new (winston.transports.Console)({ json: false, timestamp: true }),
    new winston.transports.File({ filename: thisBridgeRoot + "/node-exceptions.log", json: false })
  ],
  exitOnError: false
});

module.exports = logger;