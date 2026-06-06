from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import mss
from PIL import Image


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
SAMPLES_DIR = APP_DIR / "samples"
VALID_STATES = {"busy_stop", "typing_arrow", "ignored"}


def load_region() -> dict[str, int]:
    if not CONFIG_PATH.exists():
        raise RuntimeError("Missing config.json. Open Turnlight and set a region first.")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    region = config.get("region")
    if not isinstance(region, dict):
        raise RuntimeError("No region configured. Open Turnlight and use Set Region.")
    return {
        "left": int(region["left"]),
        "top": int(region["top"]),
        "width": int(region["width"]),
        "height": int(region["height"]),
    }


def capture_region(region: dict[str, int]) -> Image.Image:
    with mss.mss() as sct:
        shot = sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in VALID_STATES:
        states = ", ".join(sorted(VALID_STATES))
        print("Usage: python capture_sample.py <state>")
        print(f"Valid states: {states}")
        return 2

    state = sys.argv[1]
    region = load_region()
    image = capture_region(region)
    target_dir = SAMPLES_DIR / state
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = target_dir / f"{state}-{timestamp}.png"
    image.save(path)
    print(f"Saved: {path}")
    print(f"Region: {region['left']},{region['top']} {region['width']}x{region['height']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
