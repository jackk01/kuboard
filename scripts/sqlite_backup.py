#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    source_path = Path(os.getenv("SQLITE_PATH", "backend/db.sqlite3")).resolve()
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "backups").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        print(f"sqlite database not found: {source_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_path = output_dir / f"kuboard-{timestamp}.sqlite3"

    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    print(target_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
