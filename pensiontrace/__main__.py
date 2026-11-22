import argparse
from pathlib import Path

from .db import Store, pack

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["migrate", "seed", "export", "evaluate"])
parser.add_argument("--seed", type=int, default=73)
parser.add_argument("--count", type=int, default=6600)
parser.add_argument("--output", default="runtime/demo-data.json")
args = parser.parse_args()
store = Store()
if args.command == "migrate":
    store.migrate()
elif args.command == "seed":
    print("Seeded tenant" if store.seed(args.seed, args.count) else "Tenant already seeded")
else:
    data = store.snapshot("demo", 32 if args.command == "export" else 0, public=args.command == "export")
    if not data["benchmark"]:
        parser.error("Seed the synthetic tenant first")
    if args.command == "export":
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        # The public report is synthetic and carries no credentials or benchmark labels.
        target.write_text(pack(data) + "\n", encoding="utf-8")
        print(f"Exported {len(data['cases'])} cases to {target}")
    else:
        print(pack(data["benchmark"]))
