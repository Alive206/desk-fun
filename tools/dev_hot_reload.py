from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "main.py"

WATCH_DIRS = [
    ROOT / "src",
    ROOT / "assets",
]
WATCH_FILES = [
    ROOT / "main.py",
    ROOT / "pyproject.toml",
]
WATCH_SUFFIXES = {".py", ".json", ".toml", ".png"}
POLL_INTERVAL_SECONDS = 0.6


def should_watch(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    if any(part.startswith(".") for part in path.parts):
        return False
    if "__pycache__" in path.parts:
        return False
    if path.is_dir():
        return False
    return path.suffix.lower() in WATCH_SUFFIXES


def snapshot() -> dict[Path, float]:
    mtimes: dict[Path, float] = {}
    for file_path in WATCH_FILES:
        if file_path.exists() and should_watch(file_path):
            mtimes[file_path] = file_path.stat().st_mtime

    for watch_dir in WATCH_DIRS:
        if not watch_dir.exists():
            continue
        for file_path in watch_dir.rglob("*"):
            if should_watch(file_path):
                mtimes[file_path] = file_path.stat().st_mtime
    return mtimes


def start_child() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(ENTRY)],
        cwd=str(ROOT),
    )


def stop_child(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def diff_files(before: dict[Path, float], after: dict[Path, float]) -> list[Path]:
    changed: list[Path] = []
    all_files = set(before.keys()) | set(after.keys())
    for file_path in all_files:
        if before.get(file_path) != after.get(file_path):
            changed.append(file_path)
    return sorted(changed)


def main() -> int:
    print("[dev-hot-reload] Starting desktop pet...")
    process = start_child()
    current = snapshot()

    try:
        while True:
            time.sleep(POLL_INTERVAL_SECONDS)
            latest = snapshot()
            changed = diff_files(current, latest)
            if not changed:
                if process.poll() is not None:
                    print("[dev-hot-reload] App exited, restarting...")
                    process = start_child()
                continue

            shown = ", ".join(str(path.relative_to(ROOT)) for path in changed[:5])
            if len(changed) > 5:
                shown += ", ..."
            print(f"[dev-hot-reload] Change detected: {shown}")
            stop_child(process)
            process = start_child()
            current = latest
    except KeyboardInterrupt:
        print("\n[dev-hot-reload] Stopping...")
        stop_child(process)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
