var net = require('net')
  , express = require('express')
  , socketio = require('socket.io')
  , http = require('http');

var app = express();

app.use(express.static(__dirname + '/public'));
app.set('views', __dirname + '/views');
app.set('view engine', 'ejs');

app.get('/', function(req, res) {
  res.render('index', {host: req.headers.host});
});

var httpServer = http.createServer(app).listen(5678);
var io = socketio.listen(httpServer);

var server = net.createServer(function (socket) {
    var buffer = "";
// Message on socket connection
//    socket.write('Echo server\r\n');
// Echo the sent data back to the sender
//    socket.pipe(socket);
    socket.on('data', function(buf) {
        buffer += buf;
        console.log('Part data: ' + buf);
        parts = buf.toString().split(":");
        type = parts[0];
        temp = parts[1];
        if (type == 'objtemp') {
          var time = Date.now();
          io.sockets.emit('temperature-update', {temperature: parseFloat(temp), time: time})
        }
    });

    socket.on('end', function() {
        console.log('Aggregator: ' + buffer);
    });
});

server.listen(8888); // Add a host as 2nd arg to restrict access.

// Can be tested with "telnet localhost 8888"
