"""启动设备模拟器：python device/run.py 或 device/start.ps1"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

from device.config import settings


def main() -> None:
    print(f"Device simulator → http://127.0.0.1:{settings.port}")
    print(f"Cloud API base   → {settings.cloud_base_url}")
    print(f"Device DB        → {settings.database_url}")
    uvicorn.run(
        "device.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_dirs=[str(ROOT / "device")],
    )


if __name__ == "__main__":
    main()
