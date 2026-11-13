'use strict';
const http = require('node:http');
const expected = {
  'TEMP-01': { zone: 'server_room', unit: 'C' },
  'HUM-01': { zone: 'work_area', unit: '%' }
};
const isObject = x => x !== null && typeof x === 'object' && !Array.isArray(x);
const validTime = t => (typeof t === 'number' && Number.isFinite(t) && t >= 0 && t <= 8640000000000000) ||
  (typeof t === 'string' && Number.isFinite(Date.parse(t)));
function reply(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(data));
}
const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    return reply(res, 200, { status: 'ok', version: 2, endpoints: ['/api/readings', '/api/actuators'] });
  }
  if (!['/api/readings', '/api/actuators'].includes(req.url)) return reply(res, 404, { error: 'not_found' });
  if (req.method !== 'POST') return reply(res, 405, { error: 'use_POST' });
  if (!(req.headers['content-type'] || '').toLowerCase().startsWith('application/json')) {
    return reply(res, 415, { error: 'use_application_json' });
  }
  const chunks = []; let size = 0; let tooLarge = false;
  req.on('data', chunk => {
    size += chunk.length;
    if (size > 16384) { tooLarge = true; chunks.length = 0; }
    if (!tooLarge) chunks.push(chunk);
  });
  req.on('end', () => {
    if (tooLarge) return reply(res, 413, { error: 'body_too_large' });
    let data;
    try { data = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
    catch { return reply(res, 400, { error: 'invalid_json' }); }
    if (!isObject(data)) return reply(res, 400, { error: req.url === '/api/readings' ? 'invalid_reading' : 'invalid_actuator' });
    if (req.url === '/api/readings') {
      const spec = Object.hasOwn(expected, data.sensor_id) ? expected[data.sensor_id] : null;
      if (!spec || data.zone !== spec.zone || data.unit !== spec.unit ||
          typeof data.value !== 'number' || !Number.isFinite(data.value) || !validTime(data.timestamp)) {
        return reply(res, 400, { error: 'invalid_fields' });
      }
      if (data.sensor_id === 'HUM-01' && (data.value < 0 || data.value > 100)) {
        return reply(res, 400, { error: 'humidity_out_of_range' });
      }
      console.log(JSON.stringify({ received_at: new Date().toISOString(), ...data }));
      return reply(res, 200, { status: 'ok', sensor_id: data.sensor_id, value: data.value });
    }
    if (data.actuator_id !== 'FAN-01' || data.zone !== 'server_room' ||
        !['ON', 'OFF'].includes(data.state) || data.mode !== 'auto' || !validTime(data.timestamp)) {
      return reply(res, 400, { error: 'invalid_actuator_fields' });
    }
    console.log(JSON.stringify({ received_at: new Date().toISOString(), ...data }));
    reply(res, 200, { status: 'ok', actuator_id: data.actuator_id, state: data.state, mode: data.mode });
  });
  req.on('error', err => console.error('request_error:', err.message));
});
server.requestTimeout = 10000;
server.listen(8080, '0.0.0.0', () => console.log('Receiver v2 listening on :8080'));
process.on('SIGTERM', () => server.close(() => process.exit(0)));
