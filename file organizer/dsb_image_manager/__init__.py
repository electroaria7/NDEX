from __future__ import annotations

from pathlib import Path

# Keep the product folder separate while exposing the inner Python package as
# `dsb_image_manager.*` when launched from the parent DSB workspace.
_inner_package = Path(__file__).with_name("dsb_image_manager")
if _inner_package.exists():
    __path__.append(str(_inner_package))
