import random
from pathlib import Path

Path("samples/syslog").mkdir(parents=True, exist_ok=True)
actions = ["allow", "deny", "drop", "permit", "block"]
protos = ["TCP", "UDP", "ICMP"]

with open("samples/syslog/large.log", "w", encoding="utf-8") as f:
    for i in range(10000):
        pri = random.choice([134, 110, 86, 142])
        action = random.choice(actions)
        proto = random.choice(protos)
        src = f"10.0.{i % 250}.{i % 254 + 1}"
        dst = f"192.168.1.{i % 254 + 1}"
        spt = 1024 + (i % 50000)
        dpt = random.choice([53, 80, 443, 22, 8080])
        f.write(
            f"<{pri}>Sep 01 12:30:05 fw01 action={action} src={src} spt={spt} dst={dst} dpt={dpt} proto={proto} msg=\"firewall event {i}\"\n"
        )

print("Successfully generated 10,000 events in samples/syslog/large.log")
