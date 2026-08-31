from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SizingMode = Literal["fixed_width", "fixed_height", "long_edge", "fixed_dimensions"]
OutputFormat = Literal["jpeg", "png", "webp"]


@dataclass(frozen=True, slots=True)
class AspectRatio:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Aspect ratio parts must be positive.")


@dataclass(frozen=True, slots=True)
class OutputSizing:
    mode: SizingMode
    width: int | None = None
    height: int | None = None
    long_edge: int | None = None

    def __post_init__(self) -> None:
        values = {"fixed_width": self.width, "fixed_height": self.height, "long_edge": self.long_edge}
        if self.mode in values and (values[self.mode] is None or values[self.mode] <= 0):
            raise ValueError(f"{self.mode} requires a positive size.")
        if self.mode == "fixed_dimensions" and (
            self.width is None or self.width <= 0 or self.height is None or self.height <= 0
        ):
            raise ValueError("fixed_dimensions requires positive width and height.")


@dataclass(frozen=True, slots=True)
class FramePreset:
    id: str
    name: str
    version: int
    ratio: AspectRatio
    background: str
    photo_scale: float
    x: float
    y: float
    builtin: bool = False

    def __post_init__(self) -> None:
        if not 0.10 <= self.photo_scale <= 1.00:
            raise ValueError("photo_scale must be between 0.10 and 1.00.")


@dataclass(frozen=True, slots=True)
class MetadataPolicy:
    preserve_capture: bool = True
    preserve_copyright: bool = True
    remove_gps: bool = True


@dataclass(frozen=True, slots=True)
class OutputProfile:
    id: str
    name: str
    version: int
    sizing: OutputSizing
    format: OutputFormat
    quality: int
    chroma_subsampling: str
    color_space: str
    embed_icc: bool
    metadata: MetadataPolicy
    builtin: bool = False


@dataclass(frozen=True, slots=True)
class ImageOverride:
    source_path: Path
    photo_scale: float
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class SourceItem:
    path: Path
    oriented_width: int
    oriented_height: int
    has_icc: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RenderPlan:
    canvas_width: int
    canvas_height: int
    photo_width: int
    photo_height: int
    left: int
    top: int
