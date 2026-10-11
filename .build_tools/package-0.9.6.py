from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parents[1]
folder = root / 'release/NDEX_v0.9.6'
archive = root / 'release/NDEX_v0.9.6.zip'
installer = root / 'release/NDEX_Setup_0.9.6.exe'

def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()

files = sorted(path for path in folder.rglob('*') if path.is_file())
expected = {}
for line in (folder / 'SHA256SUMS.txt').read_text().splitlines():
    value, relative = line.split('  ', 1)
    expected[relative] = value
assert set(expected) == {p.relative_to(folder).as_posix() for p in files if p.name != 'SHA256SUMS.txt'}
assert all(digest(folder / name) == value for name, value in expected.items())
assert installer.is_file()
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as package:
    for path in files:
        package.write(path, (Path(folder.name) / path.relative_to(folder)).as_posix())
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None
    assert len(package.namelist()) == len(files)
    for relative, value in expected.items():
        with package.open(f'{folder.name}/{relative}') as stream:
            content = hashlib.sha256()
            for block in iter(lambda: stream.read(1024*1024), b''):
                content.update(block)
        assert content.hexdigest() == value, relative

assets = [installer, archive]
checksums = root / 'release/SHA256SUMS-0.9.6.txt'
checksums.write_text(''.join(f'{digest(path)}  {path.name}\n' for path in assets), encoding='ascii')
assets.append(checksums)
manifest = {
    'version':'0.9.6', 'channel':'beta',
    'package_file_count':len(files),
    'zip_contents_and_hashes':'passed',
    'assets':[{'name':p.name, 'size':p.stat().st_size, 'sha256':digest(p)} for p in assets],
}
(root / '.build_tools/release-0.9.6-artifacts.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest, indent=2), flush=True)
