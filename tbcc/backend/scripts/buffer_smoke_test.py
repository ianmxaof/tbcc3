"""One-off: queue a test post to Buffer (reads tbcc/.env). Run from tbcc/backend."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.buffer_graphql import buffer_target_channel_ids, create_posts_multi_channel

x_only = "--all-channels" not in sys.argv
chans = buffer_target_channel_ids(x_primary_only=x_only)
print("channels:", chans, file=sys.stderr)
if not chans:
    print("No channel ids configured", file=sys.stderr)
    sys.exit(1)
text = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "TBCC Buffer smoke test"
results = create_posts_multi_channel(text, channel_ids=chans)
print(json.dumps(results, indent=2))
