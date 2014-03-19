
var rest = require('restler'),
    Q = require('q');

var cookie_reader = require('cookie');

/* Controller Authentication */

var controllerAuth = function(controllerURL, email, password) {

    var deferredSessionData = Q.defer();

    var authDetailsObj = {
        "email": email,
        "password": password
    }
    var authDetails = JSON.stringify(authDetailsObj);

    // Define options for Django REST Client
    var controllerAuthOptions = { 
        method: "post",
        headers: {
            'Content-type': 'application/json', 
            'Accept': 'application/json'
        },
        data: authDetails
    };  

    controllerAuthURL = controllerURL + 'bridge_auth/login/'

    // Make a request to Django to get session data
    rest.post(controllerAuthURL, controllerAuthOptions).on('complete', function(data, response) {

        // If the response was good, return the session data
        if (response && response.hasOwnProperty('statusCode')) { 
            if (response.statusCode == 200) {
                cookies = cookie_reader.parse(String(response.headers['set-cookie']));
                deferredSessionData.resolve(cookies['sessionid']);
            } else {
                deferredSessionData.reject('Error from bridge controller', response, data);
            }
        } else {
            deferredSessionData.reject('There was an error authenticating to the Bridge Controller');
        }   
    });

    return deferredSessionData.promise;
}

module.exports = controllerAuth;

