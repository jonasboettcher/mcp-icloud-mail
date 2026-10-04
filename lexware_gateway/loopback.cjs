// Skybridge 2 listens on all interfaces by default. This sidecar is private.
const net = require('node:net');
const original = net.Server.prototype.listen;
net.Server.prototype.listen = function (port, ...args) {
  if (typeof port !== 'number' || typeof args[0] !== 'function') {
    throw new Error('Unexpected backend listen signature; review required');
  }
  return original.call(this, port, '127.0.0.1', ...args);
};
