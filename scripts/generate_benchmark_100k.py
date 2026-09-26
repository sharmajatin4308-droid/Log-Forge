import random
from pathlib import Path

# Deterministic seed for reproducible benchmark corpus
random.seed(42)

out_dir = Path("samples/syslog")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "benchmark_100k.log"

actions = ["allow", "deny", "drop", "permit", "block"]
protos = ["TCP", "UDP", "ICMP"]
priorities = [134, 110, 86, 142]
dpts = [53, 80, 443, 22, 8080]

with open(out_path, "w", encoding="utf-8") as f:
    for i in range(100_000):
        pri = random.choice(priorities)
        action = random.choice(actions)
        proto = random.choice(protos)
        src = f"10.0.{i % 250}.{i % 254 + 1}"
        dst = f"192.168.1.{i % 254 + 1}"
        spt = 1024 + (i % 50000)
        dpt = random.choice(dpts)
        f.write(
            f'<{pri}>Sep 01 12:30:05 fw01 action={action} src={src} spt={spt} dst={dst} dpt={dpt} proto={proto} msg="firewall event {i}"\n'
        )

line_count = 0
with open(out_path, "r", encoding="utf-8") as f:
    for _ in f:
        line_count += 1

print(f"Generated: {out_path} ({out_path.stat().st_size:,} bytes, {line_count:,} lines)")
