"""Change a manual sensor inject node through the Node-RED admin API.

Usage: python3 set_sensor.py <node_id> <value> <repeat_seconds>
An empty repeat_seconds stops the periodic sending.
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:1880"
node_id, value, repeat = sys.argv[1], sys.argv[2], sys.argv[3]

with urllib.request.urlopen(BASE + "/flows", timeout=20) as resp:
    flows = json.load(resp)

found = False
for node in flows:
    if node.get("id") == node_id:
        found = True
        node["repeat"] = repeat
        node["payload"] = value
        node["payloadType"] = "num"
if not found:
    raise SystemExit(node_id + " not found")

payload = json.dumps(flows).encode()
req = urllib.request.Request(
    BASE + "/flows",
    data=payload,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "Node-RED-Deployment-Type": "full",
    },
)
with urllib.request.urlopen(req, timeout=30) as resp:
    print("deploy", resp.status, node_id, "value=" + value, "repeat=" + repr(repeat))
