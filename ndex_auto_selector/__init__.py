from __future__ import annotations

from pathlib import Path

_inner_package = Path(__file__).with_name("ndex_auto_selector")
if _inner_package.exists():
    __path__.append(str(_inner_package))
