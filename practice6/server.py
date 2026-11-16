"""Учебный сервис хранения. Python standard library only."""
import csv, io, json, math, os, re, sqlite3, time
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
DB = Path(os.getenv('DB_PATH', '/data/telemetry.sqlite3'))
ROOT = Path(__file__).parent
# Expected contract only. No CREATE TABLE, migrations, or automatic file creation.
EXPECTED = {
 'measurements': [('id','INTEGER',0,1),('source','TEXT',1,0),('device_id','TEXT',1,0),
  ('metric','TEXT',1,0),('zone','TEXT',1,0),('timestamp','INTEGER',1,0),
  ('received_at','INTEGER',1,0),('value','REAL',1,0),('unit','TEXT',1,0),('labels','TEXT',1,0)],
 'actuator_events': [('id','INTEGER',0,1),('source','TEXT',1,0),('device_id','TEXT',1,0),
  ('zone','TEXT',1,0),('timestamp','INTEGER',1,0),('received_at','INTEGER',1,0),
  ('state','TEXT',1,0),('mode','TEXT',1,0)]
}
def connect():
 # rw opens an EXISTING file and fails rather than silently creating a new DB.
 c=sqlite3.connect(DB.resolve().as_uri()+'?mode=rw',uri=True,timeout=10)
 c.row_factory=sqlite3.Row
 return c

def init():
 if not DB.is_file():
  raise RuntimeError('Database file missing: create data/telemetry.sqlite3 manually with sqlite3 BEFORE starting storage')
 with connect() as c:
  for name,expected in EXPECTED.items():
   kind=c.execute('SELECT type FROM sqlite_master WHERE name=?',(name,)).fetchone()
   if not kind or kind[0]!='table':raise RuntimeError('Missing table: '+name+'. Create it manually in sqlite3.')
   rows=c.execute('PRAGMA table_info('+name+')').fetchall()
   actual=[(v['name'],v['type'].upper(),v['notnull'],v['pk']) for v in rows]
   # Column order may differ; names, types, PRIMARY KEY and NOT NULL must match.
   if sorted(actual)!=sorted(expected):
    raise RuntimeError('Wrong structure for '+name+'. Check .schema and PRAGMA table_info; expected '+repr(expected))
   if name=='measurements':
    labels=next(v for v in rows if v['name']=='labels')
    if labels['dflt_value'] not in ("'{}'",'"{}"'):
     raise RuntimeError("measurements.labels must have DEFAULT '{}'")
  if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise RuntimeError('SQLite integrity check failed')

def stamp(v):
 if isinstance(v,bool): raise ValueError('timestamp')
 if isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=253402300799999: return int(v)
 if isinstance(v,str):
  d=datetime.fromisoformat(v.replace('Z','+00:00'))
  if d.tzinfo is None: raise ValueError('timezone_required')
  n=int(d.timestamp()*1000)
  if 0<=n<=253402300799999: return n
 raise ValueError('timestamp')

def word(v):
 if not isinstance(v,str) or not v.strip() or len(v)>128: raise ValueError('text_field')
 return v

def number(v):
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): raise ValueError('numeric_value')
 return v

def save(path,p):
 if not isinstance(p,dict): raise ValueError('json_object_required')
 ts=stamp(p.get('timestamp')); now=int(time.time()*1000)
 with connect() as c:
  if path=='/api/readings':
   specs={'TEMP-01':('temperature','server_room','C'),'HUM-01':('humidity','work_area','%')}
   device=p.get('sensor_id')
   if device not in specs: raise ValueError('sensor_id')
   metric,zone,unit=specs[device]
   if p.get('zone')!=zone or p.get('unit')!=unit: raise ValueError('zone_or_unit')
   val=number(p.get('value'))
   if device=='HUM-01' and not 0<=val<=100: raise ValueError('humidity_range')
   cur=c.execute('INSERT INTO measurements(source,device_id,metric,zone,timestamp,received_at,value,unit) VALUES(?,?,?,?,?,?,?,?)',('node_red',device,metric,zone,ts,now,val,unit))
  elif path=='/api/actuators':
   if p.get('actuator_id')!='FAN-01' or p.get('zone')!='server_room' or p.get('state') not in ('ON','OFF') or p.get('mode')!='auto': raise ValueError('actuator_fields')
   cur=c.execute('INSERT INTO actuator_events(source,device_id,zone,timestamp,received_at,state,mode) VALUES(?,?,?,?,?,?,?)',('node_red','FAN-01','server_room',ts,now,p['state'],'auto'))
  else:
   labels=p.get('labels',{})
   if not isinstance(labels,dict) or len(json.dumps(labels))>4096: raise ValueError('labels')
   cur=c.execute('INSERT INTO measurements(source,device_id,metric,zone,timestamp,received_at,value,unit,labels) VALUES(?,?,?,?,?,?,?,?,?)',(word(p.get('source')),word(p.get('device_id')),word(p.get('metric')),word(p.get('zone')),ts,now,number(p.get('value')),word(p.get('unit')),json.dumps(labels,ensure_ascii=False)))
  rowid=cur.lastrowid
 return {'status':'stored','id':rowid}

def records(q):
 # Unified read view. Parameterized filters; never accept SQL from HTTP.
 sql='''SELECT id,'measurement' AS kind,source,device_id,metric,zone,timestamp,received_at,value,unit,'' AS state,labels FROM measurements
 UNION ALL SELECT id,'actuator',source,device_id,'fan_state',zone,timestamp,received_at,NULL,'',state,'{}' FROM actuator_events'''
 where=[]; args=[]
 for key in ('device_id','source','metric'):
  if q.get(key,[''])[0]: where.append(key+'=?');args.append(q[key][0])
 for key,op in [('from','>='),('to','<=')]:
  if q.get(key,[''])[0]:where.append('timestamp'+op+'?');args.append(stamp(float(q[key][0])))
 limit=int(q.get('limit',['500'])[0]); limit=max(1,min(limit,10000))
 sql='SELECT * FROM ('+sql+')'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY timestamp DESC,kind,id DESC LIMIT ?'
 with connect() as c:return [dict(r) for r in c.execute(sql,args+[limit])]

class Handler(BaseHTTPRequestHandler):
 def send(self,status,body,ctype='application/json; charset=utf-8',headers=None):
  if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def do_POST(self):
  path=urlparse(self.path).path
  if path not in ('/api/readings','/api/actuators','/api/metrics'):return self.send(404,{'error':'not_found'})
  if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':return self.send(415,{'error':'content_type'})
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=16384:return self.send(413,{'error':'body_size'})
   p=json.loads(self.rfile.read(n)); result=save(path,p)
   print(json.dumps({'path':path,**result},ensure_ascii=False),flush=True)
   self.send(200,result)
  except (ValueError,TypeError,KeyError,OverflowError) as e:self.send(400,{'error':'invalid_fields','detail':str(e)})
  except sqlite3.Error as e:
   print('database error:',e,flush=True);self.send(503,{'error':'database_unavailable'})
 def do_GET(self):
  u=urlparse(self.path);q=parse_qs(u.query)
  try:
   if u.path=='/':return self.send(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
   if u.path=='/health':
    with connect() as c:
     c.execute('SELECT 1 FROM measurements LIMIT 1').fetchall()
    return self.send(200,{'status':'ok','storage':'sqlite','version':2})
   if u.path=='/api/summary':
    with connect() as c:
     total=c.execute('SELECT (SELECT COUNT(*) FROM measurements)+(SELECT COUNT(*) FROM actuator_events)').fetchone()[0]
     latest=[dict(r) for r in c.execute('SELECT m.* FROM measurements m WHERE id=(SELECT id FROM measurements x WHERE x.source=m.source AND x.device_id=m.device_id AND x.metric=m.metric ORDER BY timestamp DESC,id DESC LIMIT 1) ORDER BY device_id,metric')]
     fan=c.execute('SELECT * FROM actuator_events ORDER BY timestamp DESC,id DESC LIMIT 1').fetchone()
    return self.send(200,{'total':total,'latest':latest,'fan':dict(fan) if fan else None})
   if u.path in ('/api/history','/api/export.csv'):
    data=records(q)
    if u.path=='/api/history':return self.send(200,{'rows':data,'count':len(data)})
    out=io.StringIO();fields=['id','kind','source','device_id','metric','zone','timestamp','received_at','value','unit','state','labels']
    w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
    for r in data:
     # Prevent spreadsheet formula interpretation for arbitrary metric labels.
     w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in r.items()})
    return self.send(200,('\ufeff'+out.getvalue()).encode(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename=history.csv'})
   if u.path=='/api/backup':
    dst=sqlite3.connect(':memory:')
    try:
     with connect() as src:src.backup(dst)
     blob=dst.serialize()
    finally:dst.close()
    return self.send(200,blob,'application/vnd.sqlite3',{'Content-Disposition':'attachment; filename=telemetry-backup.sqlite3'})
   self.send(404,{'error':'not_found'})
  except (ValueError,TypeError,OverflowError):self.send(400,{'error':'invalid_filter'})
  except sqlite3.Error:self.send(503,{'error':'database_unavailable'})

if __name__=='__main__':
 
 try:init()
 except (RuntimeError,sqlite3.Error) as e:
  print('STARTUP ERROR:',e,flush=True);raise SystemExit(1)
 print('SQLite storage ready; existing schema verified; no tables created',flush=True)
 ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8081'))),Handler).serve_forever()
