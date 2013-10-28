

var BridgeConcentrator = require('./bridge_concentrator.js');

bridgeConcentrator = new BridgeConcentrator(5000);

bridgeConcentrator.messages.onValue(function(value) { console.log('Bridge >', value);}); 


var ControllerSocket = require('./controller_socket.js');

controllerSocket = new ControllerSocket('54.200.16.244', 3000);

controllerSocket.commands.onValue(function(value) { console.log('Controller >', value);}); 


//bridgeConcentrator.messages.onValue(function(value) {
//    controllerSocket.socket.emit('message', value);
//});

controllerSocket.commands.onValue(function(value) {
    //bridgeConcentrator.socket.write(value + '\r\n');

    message = JSON.parse(value);
    console.log('controllerSocket', message);
    if (message.cmd == 'start') {
        bridgeConcentrator.socket.write('{ "cmd": "start" }\r\n');
    } else {
        bridgeConcentrator.socket.write('{ "cmd": "discover" }\r\n');
    }
        
});
