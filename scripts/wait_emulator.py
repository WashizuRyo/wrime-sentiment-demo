"""Wait at most 60 seconds for the local emulator, with TLS verification."""

import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

ca = Path(__file__).resolve().parents[1] / ".local/emulator/9297/ca.pem"
for _ in range(60):
    try:
        context = ssl.create_default_context(cafile=str(ca))
        with urllib.request.urlopen(
            "https://127.0.0.1:9297/__admin/health", context=context, timeout=1
        ) as response:
            if response.status == 200:
                print("AWS Emulator is ready")
                break
    except (OSError, urllib.error.URLError):
        pass
    time.sleep(1)
else:
    raise SystemExit("AWS Emulator did not become ready. Check docker compose logs.")
