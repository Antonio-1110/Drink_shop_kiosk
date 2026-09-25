// Adds an /api proxy to the Expo dev server, like the kiosk's vite.config.js,
// so the web build can call the Django backend on port 8000 without CORS.
const http = require('http');
const { getDefaultConfig } = require('expo/metro-config');

const BACKEND = { host: 'localhost', port: 8000 };

const config = getDefaultConfig(__dirname);

config.server.enhanceMiddleware = (middleware) => (req, res, next) => {
  if (!req.url.startsWith('/api/')) return middleware(req, res, next);
  const proxied = http.request(
    { ...BACKEND, method: req.method, path: req.url.replace(/^\/api/, ''),
      headers: { ...req.headers, host: `${BACKEND.host}:${BACKEND.port}` } },
    (backendRes) => {
      res.writeHead(backendRes.statusCode, backendRes.headers);
      backendRes.pipe(res);
    },
  );
  proxied.on('error', () => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Backend is not running on port 8000' }));
  });
  req.pipe(proxied);
};

module.exports = config;
