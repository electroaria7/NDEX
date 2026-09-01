from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageCms


def make_adobe_rgb_fixture(adobe_profile_path: Path, output_path: Path) -> None:
    source = Image.new("RGB", (32, 32))
    source.putdata(
        [
            (
                round(x * 255 / 31),
                round(y * 255 / 31),
                round((x + y) * 255 / 62),
            )
            for y in range(32)
            for x in range(32)
        ]
    )

    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    adobe_profile = ImageCms.getOpenProfile(str(adobe_profile_path))
    converted = ImageCms.profileToProfile(
        source,
        srgb_profile,
        adobe_profile,
        outputMode="RGB",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    converted.save(
        output_path,
        format="JPEG",
        quality=95,
        subsampling=0,
        optimize=False,
        progressive=False,
        icc_profile=adobe_profile.tobytes(),
    )

    with Image.open(output_path) as saved:
        if not saved.info.get("icc_profile"):
            raise RuntimeError(f"Generated fixture has no embedded ICC profile: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate committed color-management image fixtures.")
    parser.add_argument("--adobe-profile", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("adobe-rgb-master.jpg"),
    )
    args = parser.parse_args()
    make_adobe_rgb_fixture(args.adobe_profile, args.output)


if __name__ == "__main__":
    main()
