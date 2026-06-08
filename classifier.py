from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageOps, ImageStat

from runtime_paths import user_data_dir


DATA_DIR = user_data_dir()
SAMPLES_DIR = DATA_DIR / "samples"
DEBUG_STATE_IMAGE = DATA_DIR / "debug-state-current.png"
DEBUG_STATE_RESULT = DATA_DIR / "debug-state-result.json"

KNOWN_STATES = ("busy_stop", "typing_arrow")
SAMPLE_STATES = ("busy_stop", "typing_arrow", "ignored")
IMAGE_SIZE = (64, 64)


@dataclass(frozen=True)
class StateScore:
    state: str
    score: float
    samples: int


@dataclass(frozen=True)
class Classification:
    state: str
    confidence: float
    scores: tuple[StateScore, ...]
    reason: str

    @property
    def should_alert(self) -> bool:
        return False


def normalize(image: Image.Image) -> Image.Image:
    normalized = image.convert("L")
    normalized = ImageOps.autocontrast(normalized)
    normalized = ImageOps.fit(normalized, IMAGE_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    return normalized


def shape_classification(image: Image.Image) -> Classification | None:
    current = normalize(image)
    foreground = [
        (x, y, current.getpixel((x, y)))
        for y in range(IMAGE_SIZE[1])
        for x in range(IMAGE_SIZE[0])
        if current.getpixel((x, y)) > 50
    ]
    if len(foreground) < 80:
        return None

    cx = round(sum(x for x, _y, _v in foreground) / len(foreground))
    cy = round(sum(y for _x, y, _v in foreground) / len(foreground))
    inside: list[tuple[int, int, int]] = []
    radius = 14
    for y in range(cy - radius - 1, cy + radius + 2):
        for x in range(cx - radius - 1, cx + radius + 2):
            if 0 <= x < IMAGE_SIZE[0] and 0 <= y < IMAGE_SIZE[1] and (x - cx) ** 2 + (y - cy) ** 2 < radius**2:
                inside.append((x, y, current.getpixel((x, y))))

    if len(inside) < 80:
        return None

    median = statistics.median(v for _x, _y, v in inside)
    dark = [(x, y) for x, y, v in inside if v < median - 35]
    if len(dark) < 12:
        return None

    xs = [x for x, _y in dark]
    ys = [y for _x, y in dark]
    width = max(xs) - min(xs) + 1
    height = max(ys) - min(ys) + 1
    fill = len(dark) / max(1, width * height)
    aspect = width / max(1, height)

    if len(dark) >= 90 and 0.70 <= aspect <= 1.35 and fill >= 0.72:
        return Classification("busy_stop", min(0.99, fill), (), "shape_stop")

    if len(dark) <= 120 and fill <= 0.45:
        return Classification("typing_arrow", min(0.95, 1.0 - fill), (), "shape_arrow")

    return None


def sample_paths(samples_dir: Path, state: str) -> list[Path]:
    folder = samples_dir / state
    if not folder.exists():
        return []
    return sorted(path for path in folder.glob("*.png") if path.is_file())


def similarity(a: Image.Image, b: Image.Image) -> float:
    diff = ImageChops.difference(a, b)
    mean = ImageStat.Stat(diff).mean[0]
    return max(0.0, 1.0 - (mean / 255.0))


def top_average(values: Iterable[float], count: int = 3) -> float:
    ordered = sorted(values, reverse=True)
    if not ordered:
        return 0.0
    selected = ordered[:count]
    return sum(selected) / len(selected)


class ButtonStateClassifier:
    def __init__(self, samples_dir: Path = SAMPLES_DIR, threshold: float = 0.78, margin: float = 0.035) -> None:
        self.samples_dir = samples_dir
        self.threshold = threshold
        self.margin = margin
        self.templates: dict[str, list[Image.Image]] = {}
        self.reload()

    def reload(self) -> None:
        loaded: dict[str, list[Image.Image]] = {}
        for state in SAMPLE_STATES:
            loaded[state] = []
            for path in sample_paths(self.samples_dir, state):
                try:
                    loaded[state].append(normalize(Image.open(path)))
                except Exception:
                    continue
        self.templates = loaded

    def classify(self, image: Image.Image) -> Classification:
        current = normalize(image)
        scores: list[StateScore] = []
        for state in SAMPLE_STATES:
            templates = self.templates.get(state, [])
            state_score = top_average(similarity(current, template) for template in templates)
            scores.append(StateScore(state=state, score=state_score, samples=len(templates)))

        scores.sort(key=lambda item: item.score, reverse=True)
        best = scores[0] if scores else StateScore("unknown", 0.0, 0)
        second = scores[1] if len(scores) > 1 else StateScore("unknown", 0.0, 0)

        if best.state == "ignored" and best.samples > 0 and best.score >= self.threshold:
            return Classification("unknown", best.score, tuple(scores), "ignored match")

        if best.state in KNOWN_STATES and best.samples > 0 and best.score >= self.threshold:
            if best.score - second.score < self.margin:
                return Classification("unknown", best.score, tuple(scores), "low margin")
            return Classification(best.state, best.score, tuple(scores), "match")

        shape_result = shape_classification(image)
        if shape_result is not None:
            return shape_result

        if best.samples == 0:
            return Classification("unknown", 0.0, tuple(scores), "no samples to compare")

        if best.score < self.threshold:
            return Classification("unknown", best.score, tuple(scores), "low score")

        if best.score - second.score < self.margin:
            return Classification("unknown", best.score, tuple(scores), "low margin")

        return Classification(best.state, best.score, tuple(scores), "match")

    def save_debug(self, image: Image.Image, classification: Classification) -> None:
        DEBUG_STATE_IMAGE.parent.mkdir(parents=True, exist_ok=True)
        image.save(DEBUG_STATE_IMAGE)
        payload = {
            "state": classification.state,
            "confidence": classification.confidence,
            "reason": classification.reason,
            "scores": [
                {"state": score.state, "score": score.score, "samples": score.samples}
                for score in classification.scores
            ],
        }
        DEBUG_STATE_RESULT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
