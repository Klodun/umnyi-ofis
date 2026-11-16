import sqlite3,os,json
from pathlib import Path
c=sqlite3.connect(Path(os.getenv("DB_PATH","/data/telemetry.sqlite3")).resolve().as_uri()+"?mode=ro",uri=True);c.row_factory=sqlite3.Row
for name in ("measurements","actuator_events"):
 print(name, "rows:",c.execute("SELECT COUNT(*) FROM "+name).fetchone()[0])
 for r in c.execute("SELECT * FROM "+name+" ORDER BY id DESC LIMIT 5"):print(json.dumps(dict(r),ensure_ascii=False))
