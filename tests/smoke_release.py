"""Run the assembled Windows EXEs against disposable photos and app data.

Usage: python tests/smoke_release.py RELEASE_FOLDER EVIDENCE_FOLDER
The evidence folder must not exist. No installed app data is used or changed.
"""

from __future__ import annotations

import hashlib
import ast
import dis
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageCms

EXECUTABLES = (
    "NDEX_Launcher.exe",
    "Apps/NDEX_One.exe",
    "Apps/NDEX_Image_Manager.exe",
    "Apps/NDEX_Auto_Selector.exe",
    "Apps/NDEX_Frame.exe",
)


def packaged_version(path):
    """Read constant assignments from the bundled module without executing it."""
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(path))
    pyz_name = next(name for name, entry in archive.toc.items() if entry[-1] == "z")
    code = archive.open_embedded_archive(pyz_name).extract("ndex_common.version")
    instructions = list(dis.get_instructions(code))
    return {
        instruction.argval: instructions[index - 1].argval
        for index, instruction in enumerate(instructions)
        if index and instruction.opname == "STORE_NAME"
        and instruction.argval in {"NDEX_VERSION", "NDEX_CHANNEL"}
        and instructions[index - 1].opname == "LOAD_CONST"
    }


def source_version():
    path = Path(__file__).resolve().parents[1] / "ndex_common" / "version.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    return {
        statement.targets[0].id: ast.literal_eval(statement.value)
        for statement in module.body
        if isinstance(statement, ast.Assign)
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id in {"NDEX_VERSION", "NDEX_CHANNEL"}
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    release, work = (Path(value).resolve() for value in sys.argv[1:])
    work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, LOCALAPPDATA=str(work / "appdata"), QT_QPA_PLATFORM="offscreen")
    results = []

    versions = {}
    expected_version = source_version()
    for relative in EXECUTABLES:
        executable = release / relative
        assert executable.is_file(), f"Missing executable: {relative}"
        versions[relative] = packaged_version(executable)
        assert versions[relative] == expected_version, (relative, versions[relative], expected_version)
    (work / "packaged_versions.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")

    def run(step, exe, *args):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        command = [str(release / "Apps" / exe), *(str(arg) for arg in args)]
        result = subprocess.run(command, env=env, cwd=work, capture_output=True,
                                timeout=180, startupinfo=startup)
        (work / f"{step}.stdout.txt").write_bytes(result.stdout)
        (work / f"{step}.stderr.txt").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"{exe} failed: {result.returncode}; see {work}")
        results.append({"step": step, "exe": exe, "exit_code": result.returncode,
                        "arguments": [str(arg) for arg in args]})
        return result

    checked_files = set()
    for line in (release / "SHA256SUMS.txt").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        assert digest(release / relative) == expected, relative
        checked_files.add(relative.replace("\\", "/"))
    assert set(EXECUTABLES) <= checked_files, "An executable is missing from SHA256SUMS.txt"

    source, backup, selected, raw, output = [work / value for value in
                                            ("촬영 원본 photos", "백업", "선택 JPG", "RAW 작업", "최종 출력")]
    source.mkdir()
    selected.mkdir()
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    exif = Image.Exif()
    exif[33432] = "NDEX smoke copyright"
    exif[36867] = "2024:05:06 07:08:09"
    exif[34853] = {1: "N", 2: (40.0, 0.0, 0.0), 3: "W", 4: (88.0, 0.0, 0.0)}
    photos, masters = [], []
    for stem in ("IMG_0001", "한글_IMG_0002"):
        photo = source / f"{stem}.JPG"
        Image.new("RGB", (1200, 1800), (40, 80, 120)).save(photo, icc_profile=profile, exif=exif)
        master = source / f"{stem}.CR3"
        master.write_bytes(f"NDEX matching fixture {stem}; not a decodable RAW image".encode("utf-8"))
        photos.append(photo)
        masters.append(master)
    original = {path.name: digest(path) for path in source.iterdir()}

    run("01-backup", "NDEX_One.exe", "--source", source, "--destination", backup,
        "--backup", "--type", "jpg", "--type", "cr3", "--verify-mode", "sha256")
    for name, expected in original.items():
        matches = list(backup.rglob(name))
        assert len(matches) == 1 and digest(matches[0]) == expected, name
    manifests = work / "appdata" / "NDEX" / "manifests"
    backup_report = json.loads(next(manifests.glob("backup-*.json")).read_text(encoding="utf-8"))
    assert backup_report["counts"]["copied"] == len(original)
    for photo in photos:
        assert (backup / "2024" / "05" / "0506" / "jpg" / photo.name).is_file(), \
            f"Unicode source capture date was not preserved: {photo.name}"

    run("02-scan", "NDEX_Image_Manager.exe", "--source", backup, "--scan")
    catalog = backup / ".dsb_cache" / "catalog.sqlite"
    import sqlite3
    with sqlite3.connect(catalog) as connection:
        assert connection.execute("SELECT COUNT(*) FROM images").fetchone()[0] == len(original)
    for photo in photos:
        (selected / photo.name).write_bytes(photo.read_bytes())
    raw.mkdir()
    (raw / "기존 보관.CR3").write_bytes(b"Existing unrelated RAW; preserve it")
    (raw / "기존 보관.xmp").write_bytes(b"Existing unrelated sidecar; preserve it")
    existing = {path.name: digest(path) for path in raw.iterdir()}
    selector_args = ("--raw-source", backup, "--selected-jpg", selected,
                     "--work-folder", raw, "--copy", "--write-xmp", "--duplicate-policy", "rename")
    run("03-selector-first", "NDEX_Auto_Selector.exe", *selector_args)
    for master in masters:
        assert digest(raw / master.name) == original[master.name]
        sidecar = raw / f"{master.stem}.xmp"
        assert sidecar.is_file(), f"Selector did not write {sidecar.name}"
        # Represent an edit made after export. A repeated rename operation must
        # neither create a numbered RAW nor rewrite these user-owned bytes.
        sidecar.write_bytes(sidecar.read_bytes() + b"\n<!-- user edit must survive -->\n")
    report = json.loads((manifests / "latest-auto_selector-extract.json").read_text(encoding="utf-8"))
    assert report["counts"]["copied"] == len(masters)
    assert {name: digest(raw / name) for name in existing} == existing
    first_export = {path.name: digest(path) for path in raw.iterdir()}
    run("04-selector-repeat", "NDEX_Auto_Selector.exe", *selector_args,
        "--xmp-rating", "1", "--xmp-label", "Must not replace existing edits")
    assert {path.name: digest(path) for path in raw.iterdir()} == first_export, \
        "Selector rerun duplicated RAW files or changed existing RAW/XMP bytes"
    repeated = json.loads((manifests / "latest-auto_selector-extract.json").read_text(encoding="utf-8"))
    assert repeated["counts"]["copied"] == 0
    assert repeated["counts"]["skipped"] == len(masters)
    assert repeated["counts"]["failed"] == 0

    result = run("05-frame-export", "NDEX_Frame.exe", "--smoke-export", photos[-1], output)
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
                "packaged_versions": versions, "unicode_paths_and_names": "passed",
                "selector_repeat": {"counts": repeated["counts"], "preserved_hashes": first_export},
                "frame": payload, "raw_fixture": "matching/copy only; no real-camera RAW decoding",
                "gui_interaction": "not covered by this CLI smoke"}
    (work / "result.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Packaged CLI smoke passed: {work / 'result.json'}")


if __name__ == "__main__":
    main()
