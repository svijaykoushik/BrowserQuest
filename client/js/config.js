
define(['text!../config/config_build.json'],
function(build) {
    var parsedBuild = {};
    try {
        parsedBuild = JSON.parse(build);
    } catch(e) {}

    var defaultHost = (typeof window !== 'undefined' && window.location && window.location.hostname) ? window.location.hostname : "localhost";
    var defaultPort = (typeof window !== 'undefined' && window.location && window.location.port) ? parseInt(window.location.port, 10) : (parsedBuild.port || 39080);

    var config = {
        dev: {
            host: parsedBuild.host || defaultHost,
            port: parsedBuild.port || defaultPort,
            dispatcher: false
        },
        build: parsedBuild
    };
    
    //>>excludeStart("prodHost", pragmas.prodHost);
    require(['text!../config/config_local.json'], function(local) {
        try {
            config.local = JSON.parse(local);
            if (config.local.host) config.dev.host = config.local.host;
            if (config.local.port) config.dev.port = config.local.port;
        } catch(e) {
            // Exception triggered when config_local.json does not exist. Nothing to do here.
        }
    });
    //>>excludeEnd("prodHost");
    
    return config;
});