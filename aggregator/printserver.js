var net = require('net');

var server = net.createServer(function (socket) {
    var buffer = "";
// Message on socket connection
//    socket.write('Echo server\r\n');
// Echo the sent data back to the sender
//    socket.pipe(socket);
    socket.on('data', function(buf) {
        buffer += buf;
        console.log('Part data: ' + buf);
    });

    socket.on('end', function() {
        console.log('Aggregator: ' + buffer);
    });
});

server.listen(8888); // Add a host as 2nd arg to restrict access.

// Can be tested with "telnet localhost 8888"
