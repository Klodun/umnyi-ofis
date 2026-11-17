'use strict';
const http = require('node:http');
const expected = {
  'TEMP-01': { zone: 'server_room', unit: 'C' },
  'HUM-01': { zone: 'work_area', unit: '%' }
};
const isObject = x => x !== null && typeof x === 'object' && !Array.isArray(x);
const validTime = t => (typeof t === 'number' && Number.isFinite(t) && t >= 0 && t <= 8640000000000000) ||
  (typeof t === 'string' && Number.isFinite(Date.parse(t)));
// Latest accepted values are kept in memory for monitoring only.
const bootTime = Date.now() / 1000;
const sensorState = Object.fromEntries(Object.keys(expected).map(id => [id, { value: NaN, sourceTime: 0, receivedTime: null }]));
let fanState = NaN, modeAuto = NaN;
function metrics() {
  const now = Date.now() / 1000;
  const lines = [];
  function metric(name, help, samples) {
    lines.push('# HELP ' + name + ' ' + help, '# TYPE ' + name + ' gauge');
    for (const [labels, value] of samples) lines.push(name + labels + ' ' + (Number.isNaN(value) ? 'NaN' : value));
  }
  metric('office_temperature_celsius', 'Latest accepted server room temperature.', [['{sensor_id="TEMP-01",zone="server_room"}', sensorState['TEMP-01'].value]]);
  metric('office_humidity_percent', 'Latest accepted work area relative humidity.', [['{sensor_id="HUM-01",zone="work_area"}', sensorState['HUM-01'].value]]);
  metric('office_fan_on', 'Last reported fan state: 1 ON, 0 OFF; NaN before first report.', [['{actuator_id="FAN-01",zone="server_room"}', fanState]]);
  metric('office_control_mode_auto', 'Last reported mode: 1 auto; NaN before first fan report.', [['{actuator_id="FAN-01"}', modeAuto]]);
  metric('office_sensor_last_reading_timestamp_seconds', 'Timestamp supplied by sensor, Unix seconds; 0 means no reading yet.', Object.entries(sensorState).map(([id, st]) => ['{sensor_id="' + id + '"}', st.sourceTime]));
  metric('office_sensor_has_reading', 'Whether any valid reading was accepted since receiver startup.', Object.entries(sensorState).map(([id, st]) => ['{sensor_id="' + id + '"}', st.receivedTime === null ? 0 : 1]));
  metric('office_sensor_age_seconds', 'Seconds since last valid HTTP reading received by CTRL; before first reading since startup.', Object.entries(sensorState).map(([id, st]) => ['{sensor_id="' + id + '"}', Math.max(0, now - (st.receivedTime ?? bootTime))]));
  return lines.join('\n') + '\n';
}
function reply(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(data));
}
const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/metrics') {
    res.writeHead(200, { 'Content-Type': 'text/plain; version=0.0.4; charset=utf-8', 'Cache-Control': 'no-store' });
    return res.end(metrics());
  }
  if (req.method === 'GET' && req.url === '/health') {
    return reply(res, 200, { status: 'ok', version: 3, endpoints: ['/api/readings', '/api/actuators', '/metrics'] });
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
      sensorState[data.sensor_id] = {
        value: data.value,
        sourceTime: typeof data.timestamp === 'number' ? data.timestamp / 1000 : Date.parse(data.timestamp) / 1000,
        receivedTime: Date.now() / 1000
      };
      console.log(JSON.stringify({ received_at: new Date().toISOString(), ...data }));
      return reply(res, 200, { status: 'ok', sensor_id: data.sensor_id, value: data.value });
    }
    if (data.actuator_id !== 'FAN-01' || data.zone !== 'server_room' ||
        !['ON', 'OFF'].includes(data.state) || data.mode !== 'auto' || !validTime(data.timestamp)) {
      return reply(res, 400, { error: 'invalid_actuator_fields' });
    }
    fanState = data.state === 'ON' ? 1 : 0;
    modeAuto = 1;
    console.log(JSON.stringify({ received_at: new Date().toISOString(), ...data }));
    reply(res, 200, { status: 'ok', actuator_id: data.actuator_id, state: data.state, mode: data.mode });
  });
  req.on('error', err => console.error('request_error:', err.message));
});
server.requestTimeout = 10000;
server.listen(8080, '0.0.0.0', () => console.log('Receiver v3 with /metrics listening on :8080'));
process.on('SIGTERM', () => server.close(() => process.exit(0)));
