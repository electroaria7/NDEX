"""Built-in and user-defined NDEX Frame presets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from ndex_common import settings
from ndex_common.jsonio import write_json_atomic
from ndex_frame.core.models import AspectRatio, FramePreset, MetadataPolicy, OutputProfile, OutputSizing

PresetKind = Literal["frame", "output"]
SettingsReader = Callable[[str, dict[str, str]], dict[str, str]]
SettingsWriter = Callable[[str, dict[str, str]], None]
_PRESET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SIZING_MODES = {"fixed_width", "fixed_height", "long_edge", "fixed_dimensions"}
_FORMATS = {"jpeg", "png", "webp"}


@dataclass(frozen=True, slots=True)
class PresetError(ValueError):
    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class PresetStore:
    """Loads packaged presets and persists custom presets below *root*."""

    def __init__(
        self,
        root: Path,
        settings_reader: SettingsReader = settings.get_section,
        settings_writer: SettingsWriter = settings.update_section,
    ) -> None:
        self.root = Path(root)
        self._settings_reader = settings_reader
        self._settings_writer = settings_writer
        self.errors: list[PresetError] = []

    def list_frames(self) -> tuple[FramePreset, ...]:
        return tuple(self._load("frame"))

    def list_outputs(self) -> tuple[OutputProfile, ...]:
        return tuple(self._load("output"))

    def save_frame(self, preset: FramePreset) -> None:
        self._save(preset, "frame")

    def save_output(self, preset: OutputProfile) -> None:
        self._save(preset, "output")

    def delete_custom(self, preset_id: str, *, kind: PresetKind) -> None:
        if preset_id.startswith("builtin."):
            raise ValueError("Built-in presets cannot be deleted.")
        self._validate_id(preset_id)
        self._custom_path(kind, preset_id).unlink(missing_ok=True)

    def set_default_frame(self, preset_id: str) -> None:
        self._set_default("default_frame_id", preset_id, self.list_frames())

    def set_default_output(self, preset_id: str) -> None:
        self._set_default("default_output_id", preset_id, self.list_outputs())

    def default_frame(self) -> FramePreset:
        return self._default("default_frame_id", self.list_frames(), "builtin.white-3x4")

    def default_output(self) -> OutputProfile:
        return self._default("default_output_id", self.list_outputs(), "builtin.instagram-feed-hq")

    def _load(self, kind: PresetKind) -> list[FramePreset | OutputProfile]:
        self.errors = []
        loaded = self._load_directory(self._builtin_directory(kind), kind, builtin=True)
        loaded.extend(self._load_directory(self._custom_directory(kind), kind, builtin=False))
        return sorted(loaded, key=lambda preset: (not preset.builtin, preset.id))

    def _load_directory(
        self, directory: Path, kind: PresetKind, *, builtin: bool
    ) -> list[FramePreset | OutputProfile]:
        if not directory.exists():
            return []
        loaded: list[FramePreset | OutputProfile] = []
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                preset = _frame_from_dict(data, builtin, path) if kind == "frame" else _output_from_dict(data, builtin, path)
                loaded.append(preset)
            except (OSError, json.JSONDecodeError, PresetError) as error:
                self.errors.append(error if isinstance(error, PresetError) else PresetError(path, str(error)))
        return loaded

    def _save(self, preset: FramePreset | OutputProfile, kind: PresetKind) -> None:
        if preset.id.startswith("builtin."):
            raise ValueError("Custom presets cannot use a built-in identifier.")
        self._validate_id(preset.id)
        write_json_atomic(self._custom_path(kind, preset.id), _frame_to_dict(preset) if kind == "frame" else _output_to_dict(preset))

    def _set_default(
        self, key: str, preset_id: str, presets: tuple[FramePreset | OutputProfile, ...]
    ) -> None:
        if preset_id not in {preset.id for preset in presets}:
            raise ValueError(f"Unknown preset: {preset_id}")
        self._settings_writer("frame", {key: preset_id})

    def _default(
        self, key: str, presets: tuple[FramePreset | OutputProfile, ...], fallback_id: str
    ) -> FramePreset | OutputProfile:
        default_id = self._settings_reader("frame", {key: fallback_id}).get(key, fallback_id)
        by_id = {preset.id: preset for preset in presets}
        selected = by_id.get(default_id)
        if selected is not None:
            return selected
        fallback = by_id[fallback_id]
        self._settings_writer("frame", {key: fallback_id})
        return fallback

    def _builtin_directory(self, kind: PresetKind) -> Path:
        return Path(__file__).parents[1] / "resources" / "presets" / kind

    def _custom_directory(self, kind: PresetKind) -> Path:
        return self.root / "presets" / kind

    def _custom_path(self, kind: PresetKind, preset_id: str) -> Path:
        return self._custom_directory(kind) / f"{preset_id}.json"

    @staticmethod
    def _validate_id(preset_id: str) -> None:
        if not isinstance(preset_id, str) or not _PRESET_ID.fullmatch(preset_id):
            raise ValueError("Preset id must be a safe, non-empty identifier.")


def _frame_from_dict(data: Any, builtin: bool, path: Path = Path("<memory>")) -> FramePreset:
    values = _object(data, path, {"id", "name", "version", "ratio", "background", "photo_scale", "x", "y"})
    ratio = _object(values["ratio"], path, {"width", "height"}, "ratio")
    try:
        return FramePreset(
            _string(values["id"], path, "id"), _string(values["name"], path, "name"),
            _positive_int(values["version"], path, "version"),
            AspectRatio(_positive_int(ratio["width"], path, "ratio.width"), _positive_int(ratio["height"], path, "ratio.height")),
            _string(values["background"], path, "background"), _number(values["photo_scale"], path, "photo_scale"),
            _number(values["x"], path, "x"), _number(values["y"], path, "y"), builtin,
        )
    except (KeyError, ValueError) as error:
        raise PresetError(path, str(error)) from error


def _output_from_dict(data: Any, builtin: bool, path: Path = Path("<memory>")) -> OutputProfile:
    values = _object(data, path, {"id", "name", "version", "sizing", "format", "quality", "chroma_subsampling", "color_space", "embed_icc", "metadata"})
    sizing = _object(values["sizing"], path, {"mode"}, "sizing", optional={"width", "height", "long_edge"})
    metadata = _object(values["metadata"], path, {"preserve_capture", "preserve_copyright", "remove_gps"}, "metadata")
    try:
        mode = _string(sizing["mode"], path, "sizing.mode")
        if mode not in _SIZING_MODES:
            raise ValueError("sizing.mode is invalid")
        image_format = _string(values["format"], path, "format")
        if image_format not in _FORMATS:
            raise ValueError("format is invalid")
        quality = _positive_int(values["quality"], path, "quality")
        if quality > 100:
            raise ValueError("quality must be at most 100")
        return OutputProfile(
            _string(values["id"], path, "id"), _string(values["name"], path, "name"), _positive_int(values["version"], path, "version"),
            OutputSizing(mode, width=_optional_int(sizing.get("width"), path, "sizing.width"), height=_optional_int(sizing.get("height"), path, "sizing.height"), long_edge=_optional_int(sizing.get("long_edge"), path, "sizing.long_edge")),
            image_format, quality, _string(values["chroma_subsampling"], path, "chroma_subsampling"), _string(values["color_space"], path, "color_space"),
            _boolean(values["embed_icc"], path, "embed_icc"), MetadataPolicy(
                _boolean(metadata["preserve_capture"], path, "metadata.preserve_capture"),
                _boolean(metadata["preserve_copyright"], path, "metadata.preserve_copyright"),
                _boolean(metadata["remove_gps"], path, "metadata.remove_gps"),
            ), builtin,
        )
    except (KeyError, ValueError) as error:
        raise PresetError(path, str(error)) from error


def _object(value: Any, path: Path, required: set[str], label: str = "preset", optional: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PresetError(path, f"{label} must be an object")
    allowed = required | (optional or set())
    missing, extra = required - value.keys(), value.keys() - allowed
    if missing:
        raise PresetError(path, f"{label} is missing {', '.join(sorted(missing))}")
    if extra:
        raise PresetError(path, f"{label} has unknown fields: {', '.join(sorted(extra))}")
    return value


def _string(value: Any, path: Path, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _positive_int(value: Any, path: Path, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _optional_int(value: Any, path: Path, label: str) -> int | None:
    return None if value is None else _positive_int(value, path, label)


def _number(value: Any, path: Path, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    return float(value)


def _boolean(value: Any, path: Path, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _frame_to_dict(preset: FramePreset | OutputProfile) -> dict[str, Any]:
    assert isinstance(preset, FramePreset)
    return {"id": preset.id, "name": preset.name, "version": preset.version, "ratio": {"width": preset.ratio.width, "height": preset.ratio.height}, "background": preset.background, "photo_scale": preset.photo_scale, "x": preset.x, "y": preset.y}


def _output_to_dict(preset: FramePreset | OutputProfile) -> dict[str, Any]:
    assert isinstance(preset, OutputProfile)
    sizing = {"mode": preset.sizing.mode}
    for key in ("width", "height", "long_edge"):
        value = getattr(preset.sizing, key)
        if value is not None:
            sizing[key] = value
    return {"id": preset.id, "name": preset.name, "version": preset.version, "sizing": sizing, "format": preset.format, "quality": preset.quality, "chroma_subsampling": preset.chroma_subsampling, "color_space": preset.color_space, "embed_icc": preset.embed_icc, "metadata": {"preserve_capture": preset.metadata.preserve_capture, "preserve_copyright": preset.metadata.preserve_copyright, "remove_gps": preset.metadata.remove_gps}}
