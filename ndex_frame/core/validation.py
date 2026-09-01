"""Preflight validation helpers for NDEX Frame jobs."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def validate_output_directory(path: Path) -> Path:
    """Create and probe an output directory without leaving probe files behind."""
    output_dir = Path(path).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not output_dir.is_dir():
        raise NotADirectoryError(output_dir)

    for _ in range(8):
        probe = output_dir / f".{uuid4().hex}.ndex_probe"
        owned = False
        try:
            with probe.open("xb") as handle:
                owned = True
                handle.write(b"NDEX Frame write probe")
            return output_dir
        except FileExistsError:
            continue
        finally:
            if owned:
                probe.unlink(missing_ok=True)
    raise OSError(f"Could not allocate a unique write probe in {output_dir}")
