import json
import random
from pathlib import Path

# Deterministic seed for 100% reproducible benchmark corpus
random.seed(42)

out_dir = Path("samples")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "benchmark_10k_mixed.log"

actions = ["allow", "deny", "drop", "permit", "block"]
protos = ["TCP", "UDP", "ICMP"]
priorities = [134, 110, 86, 142]
dpts = [53, 80, 443, 22, 8080]
vendors = ["Cisco", "Fortinet", "CheckPoint", "PaloAlto", "Juniper"]
products = ["ASA", "FortiGate", "VPN-1", "PAN-OS", "SRX"]

events = []

# 1. 2,500 Syslog events (RFC 3164 BSD)
for i in range(2500):
    pri = random.choice(priorities)
    action = random.choice(actions)
    proto = random.choice(protos)
    src = f"10.0.{i % 250}.{i % 254 + 1}"
    dst = f"192.168.1.{i % 254 + 1}"
    spt = 1024 + (i % 50000)
    dpt = random.choice(dpts)
    line = f'<{pri}>Sep 01 12:30:05 fw01 action={action} src={src} spt={spt} dst={dst} dpt={dpt} proto={proto} msg="firewall event {i}"'
    events.append(line)

# 2. 2,500 CEF events
for i in range(2500):
    vendor = random.choice(vendors)
    product = random.choice(products)
    action = random.choice(actions)
    proto = random.choice(protos)
    src = f"172.16.{i % 250}.{i % 254 + 1}"
    dst = f"10.10.{i % 250}.{i % 254 + 1}"
    spt = 2000 + (i % 40000)
    dpt = random.choice(dpts)
    sev = random.choice([1, 3, 5, 7, 8])
    line = f"CEF:0|{vendor}|{product}|1.0|100{i % 10}|Traffic {action.capitalize()}|{sev}|src={src} spt={spt} dst={dst} dpt={dpt} proto={proto} act={action} rt=Sep 01 2024 12:30:05 UTC msg=Event_{i}"
    events.append(line)

# 3. 2,500 Cisco ASA events
for i in range(2500):
    src = f"10.20.{i % 250}.{i % 254 + 1}"
    dst = f"198.51.100.{i % 254 + 1}"
    spt = 3000 + (i % 30000)
    dpt = random.choice(dpts)
    if i % 2 == 0:
        line = f"Sep 01 12:30:05 fw01 %ASA-4-106001: Inbound TCP connection denied from {src}/{spt} to {dst}/{dpt} flags SYN on interface outside"
    else:
        line = f"Sep 01 12:30:05 fw01 %ASA-6-302013: Built inbound TCP connection {100000 + i} for outside:{src}/{spt} to inside:{dst}/{dpt}"
    events.append(line)

# 4. 2,500 JSON events
for i in range(2500):
    src = f"192.168.10.{i % 254 + 1}"
    dst = f"203.0.113.{i % 254 + 1}"
    spt = 4000 + (i % 40000)
    dpt = random.choice(dpts)
    proto = random.choice(protos)
    act = random.choice(actions)
    obj = {
        "timestamp": "2024-09-01T12:30:05Z",
        "event": f"network_flow_{i}",
        "src_ip": src,
        "src_port": spt,
        "destination_ip": dst,
        "destination_port": dpt,
        "protocol": proto,
        "action": act,
        "message": f"flow event {i}"
    }
    events.append(json.dumps(obj))

# Shuffle deterministically to create an interleaved realistic multi-format stream
random.shuffle(events)

assert len(events) == 10000

with open(out_path, "w", encoding="utf-8") as f:
    for ev in events:
        f.write(ev + "\n")

print(f"Generated {out_path} with {len(events)} events ({out_path.stat().st_size:,} bytes)")
