"""Run the assembled Windows EXEs against disposable photos and app data.

Usage: python tests/smoke_release.py RELEASE_FOLDER EVIDENCE_FOLDER
The evidence folder must not exist. No installed app data is used or changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageCms


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    release, work = (Path(value).resolve() for value in sys.argv[1:])
    work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, LOCALAPPDATA=str(work / "appdata"), QT_QPA_PLATFORM="offscreen")
    results = []

    def run(exe, *args):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        command = [str(release / "Apps" / exe), *(str(arg) for arg in args)]
        result = subprocess.run(command, env=env, cwd=work, capture_output=True,
                                timeout=180, startupinfo=startup)
        (work / f"{exe}.stdout.txt").write_bytes(result.stdout)
        (work / f"{exe}.stderr.txt").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"{exe} failed: {result.returncode}; see {work}")
        results.append({"exe": exe, "exit_code": result.returncode})
        return result

    for line in (release / "SHA256SUMS.txt").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        assert digest(release / relative) == expected, relative

    source, backup, selected, raw, output = [work / value for value in
                                            ("camera photos", "backup", "selected", "raw work", "output")]
    source.mkdir()
    selected.mkdir()
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    exif = Image.Exif()
    exif[33432] = "NDEX smoke copyright"
    exif[34853] = {1: "N", 2: (40.0, 0.0, 0.0), 3: "W", 4: (88.0, 0.0, 0.0)}
    photo = source / "IMG_0001.JPG"
    Image.new("RGB", (1200, 1800), (40, 80, 120)).save(photo, icc_profile=profile, exif=exif)
    master = source / "IMG_0001.CR3"
    master.write_bytes(b"NDEX matching fixture; not a decodable RAW image")
    original = {path.name: digest(path) for path in source.iterdir()}

    run("NDEX_One.exe", "--source", source, "--destination", backup,
        "--backup", "--type", "jpg", "--type", "cr3", "--verify-mode", "sha256")
    for name, expected in original.items():
        matches = list(backup.rglob(name))
        assert len(matches) == 1 and digest(matches[0]) == expected, name
    manifests = work / "appdata" / "NDEX" / "manifests"
    backup_report = json.loads(next(manifests.glob("backup-*.json")).read_text(encoding="utf-8"))
    assert backup_report["counts"]["copied"] == 2

    run("NDEX_Image_Manager.exe", "--source", backup, "--scan")
    catalog = backup / ".dsb_cache" / "catalog.sqlite"
    import sqlite3
    with sqlite3.connect(catalog) as connection:
        assert connection.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 2
    (selected / photo.name).write_bytes(photo.read_bytes())
    run("NDEX_Auto_Selector.exe", "--raw-source", backup, "--selected-jpg", selected,
        "--work-folder", raw, "--copy", "--write-xmp")
    assert digest(raw / master.name) == original[master.name]
    assert list(raw.glob("*.xmp")), "Selector did not write XMP"
    report = json.loads(next(manifests.glob("extract-*.json")).read_text(encoding="utf-8"))
    assert report["counts"]["copied"] == 1

    result = run("NDEX_Frame.exe", "--smoke-export", photo, output)
    payload = next(json.loads(line) for line in result.stdout.decode("utf-8").splitlines()
                   if line.strip().startswith("{"))
    assert payload["exported"] == 1 and payload["failed"] == 0
    with Image.open(payload["items"][0]["destination"]) as image:
        assert image.size == (1080, 1440) and image.format == "JPEG"
        assert image.info.get("icc_profile")
        assert image.getexif().get(33432) == "NDEX smoke copyright"
        assert 34853 not in image.getexif()
    assert {path.name: digest(path) for path in source.iterdir()} == original
    evidence = {"release": str(release), "checks": results,
                "checksums": "passed", "original_hashes": original,
                "frame": payload, "raw_fixture": "matching only; not RAW decoding"}
    (work / "result.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Packaged CLI smoke passed: {work / 'result.json'}")


if __name__ == "__main__":
    main()
