"""Recording paths and offline layout migration."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import re
import json
from functools import lru_cache

MEDIA_STORAGE_LAYOUT = "media_storage_layout"
FLAT = "Flat"
DATED = "Year/month/day"


@lru_cache(maxsize=32)
def _historical_correction(root):
    """Load the local archive correction once per process, during setup."""
    path = Path(root) / ".recording-date-correction.json"
    if not path.exists():
        return None
    correction = json.loads(path.read_text())
    if correction.get("version") != 1:
        raise ValueError("Unsupported recording date correction version")
    for key in ("offset_seconds", "raw_before"):
        if type(correction.get(key)) is not int:
            raise ValueError(f"Invalid recording date correction: {key}")
    return correction


def recording_path(root, folder, filename, layout, timezone):
    """Use the recording start time, including for hub child filenames."""
    path = Path(root) / folder
    if layout == DATED:
        start = int(Path(filename).stem.rsplit("-", 2)[-2])
        correction = _historical_correction(str(Path(root)))
        if correction and start < correction["raw_before"]:
            start += correction["offset_seconds"]
        path /= datetime.fromtimestamp(start, ZoneInfo(timezone)).strftime("%Y/%m/%d")
    return path / filename


def recording_files(directory):
    """Return relative paths without following directory symlinks."""
    root = Path(directory)
    return [str(p.relative_to(root)) for p in root.rglob("*")
            if p.is_file() and not p.is_symlink()]


def migrate_layout(root, layout, timezone):
    """Move completed media before camera tasks start; refuse collisions."""
    root = Path(root)
    moves = []
    targets = set()
    for folder, extension in (("videos", ".mp4"), ("thumbs", ".jpg")):
        for relative in recording_files(root / folder):
            source = root / folder / relative
            if source.suffix != extension or not re.fullmatch(
                r"(?:.+-)?[0-9]+-[0-9]+", source.stem
            ):
                continue
            target = recording_path(root, folder, source.name, layout, timezone)
            if source == target:
                continue
            if target.exists() or target in targets:
                raise ValueError(f"Recording layout destination already exists: {target}")
            targets.add(target)
            moves.append((source, target))
    for source, target in moves:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
    for folder in ("videos", "thumbs"):
        for path in sorted((root / folder).rglob("*"), reverse=True):
            if path.is_dir() and not path.is_symlink():
                try:
                    path.rmdir()
                except OSError:
                    pass
    return len(moves)
