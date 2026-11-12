'use strict';
const http = require('node:http');
const expected = {
  'TEMP-01': { zone: 'server_room', unit: 'C' },
  'HUM-01': { zone: 'work_area', unit: '%' }
};
function reply(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(data));
}
const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    return reply(res, 200, { status: 'ok' });
  }
  if (req.url !== '/api/readings') return reply(res, 404, { error: 'not_found' });
  if (req.method !== 'POST') return reply(res, 405, { error: 'use_POST' });
  if (!(req.headers['content-type'] || '').toLowerCase().startsWith('application/json')) {
    return reply(res, 415, { error: 'use_application_json' });
  }
  let body = ''; let size = 0; let tooLarge = false;
  req.on('data', chunk => {
    size += chunk.length;
    if (size > 16384) { tooLarge = true; body = ''; }
    if (!tooLarge) body += chunk.toString('utf8');
  });
  req.on('end', () => {
    if (tooLarge) return reply(res, 413, { error: 'body_too_large' });
    let reading;
    try { reading = JSON.parse(body); }
    catch { return reply(res, 400, { error: 'invalid_json' }); }
    if (!reading || typeof reading !== 'object' || Array.isArray(reading)) {
      return reply(res, 400, { error: 'invalid_reading' });
    }
    const spec = expected[reading.sensor_id];
    if (!spec || reading.zone !== spec.zone || reading.unit !== spec.unit ||
        typeof reading.value !== 'number' || !Number.isFinite(reading.value) ||
        !((typeof reading.timestamp === 'number' && Number.isFinite(reading.timestamp) && reading.timestamp >= 0 && reading.timestamp <= 8640000000000000) || (typeof reading.timestamp === 'string' && Number.isFinite(Date.parse(reading.timestamp))))) {
      return reply(res, 400, { error: 'invalid_fields' });
    }
    if (reading.sensor_id === 'HUM-01' && (reading.value < 0 || reading.value > 100)) {
      return reply(res, 400, { error: 'humidity_out_of_range' });
    }
    console.log(JSON.stringify({ received_at: new Date().toISOString(), ...reading }));
    reply(res, 200, { status: 'ok', sensor_id: reading.sensor_id, value: reading.value });
  });
  req.on('error', err => console.error('request_error:', err.message));
});
server.requestTimeout = 10000;
server.listen(8080, '0.0.0.0', () => console.log('Receiver listening on :8080'));
process.on('SIGTERM', () => server.close(() => process.exit(0)));
