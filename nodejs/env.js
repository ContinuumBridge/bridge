
var getenv = require('getenv');

// Get some values from the environment
CONTROLLER_API = "http://" + getenv('CB_DJANGO_CONTROLLER_ADDR', '54.194.73.211:8000') + "/api/bridge/v1/";
logger.info('CONTROLLER_API', CONTROLLER_API);

CONTROLLER_SOCKET = "http://" + getenv('CB_NODE_CONTROLLER_ADDR', '54.194.73.211');
logger.info('CONTROLLER_SOCKET', CONTROLLER_SOCKET);

BRIDGE_KEY = getenv('CB_BRIDGE_KEY', '930f0f10BOd/FfDpoYEilLJN+eZTvWTUseRgGpDw8WmzKGHsPo/97Y1jM2Dz9vfE');
logger.info('BRIDGE_KEY', BRIDGE_KEY);