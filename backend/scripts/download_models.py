"""Pre-download the Kokoro TTS model (~310 MB) so the first voice session doesn't block on it.

Downloads resume from a .part file and are renamed only when complete, so an interrupted
run never leaves a truncated model that looks installed.

Run from backend/:  python -m scripts.download_models
"""

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.models import KOKORO_FILES  # noqa: E402


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"ok        {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    offset = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with requests.get(url, stream=True, timeout=60, headers=headers) as resp:
        if resp.status_code == 416:  # already fully downloaded
            part.rename(dest)
            return
        resp.raise_for_status()
        if offset and resp.status_code != 206:  # server ignored Range: start over
            offset = 0
        total = offset + int(resp.headers.get("content-length", 0))
        done = offset
        with open(part, "ab" if offset else "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r{dest.name}: {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()
    part.rename(dest)


def main(attempts: int = 30) -> None:
    for url, dest in KOKORO_FILES:
        for attempt in range(1, attempts + 1):
            try:
                download(url, dest)
                break
            except requests.RequestException as e:
                print(f"\n{dest.name}: {type(e).__name__}, resuming (attempt {attempt}/{attempts})")
                time.sleep(min(2 * attempt, 30))
        else:
            sys.exit(f"Could not download {dest.name}")


if __name__ == "__main__":
    main()
