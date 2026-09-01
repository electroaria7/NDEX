# Packaged NDEX Frame smoke: hidden --smoke-export on the windowed EXE.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\ndex_frame\tests\smoke_packaged.ps1

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$exe = Join-Path $repoRoot "ndex_frame\dist\NDEX_Frame.exe"
if (-not (Test-Path $exe)) {
    throw "Missing packaged executable: $exe"
}

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("ndex-frame-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $work | Out-Null
$source = Join-Path $work "source.jpg"
$outputDir = Join-Path $work "out"
$stdoutFile = Join-Path $work "stdout.txt"
$stderrFile = Join-Path $work "stderr.txt"
$verifyScript = Join-Path $work "verify_smoke.py"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

try {
    python -c @"
from pathlib import Path
from PIL import Image, ImageCms

source = Path(r'$source')
profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
exif = Image.Exif()
exif[33432] = 'NDEX Frame copyright'
exif[34853] = {
    1: 'N',
    2: (40.0, 0.0, 0.0),
    3: 'W',
    4: (88.0, 0.0, 0.0),
}
Image.new('RGB', (1200, 1800), (40, 80, 120)).save(
    source,
    format='JPEG',
    quality=95,
    icc_profile=profile.tobytes(),
    exif=exif,
)
"@
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create 1200x1800 sRGB JPEG smoke source"
    }

    $hashBefore = (Get-FileHash -Algorithm SHA256 -Path $source).Hash
    $quotedExe = $exe.Replace('"', '""')
    $quotedSource = $source.Replace('"', '""')
    $quotedOutput = $outputDir.Replace('"', '""')
    $quotedStdout = $stdoutFile.Replace('"', '""')
    $quotedStderr = $stderrFile.Replace('"', '""')
    $cmd = '"{0}" --smoke-export "{1}" "{2}" > "{3}" 2> "{4}"' -f $quotedExe, $quotedSource, $quotedOutput, $quotedStdout, $quotedStderr
    cmd.exe /c $cmd
    if ($LASTEXITCODE -ne 0) {
        $stderrText = ""
        $stdoutText = ""
        if (Test-Path $stderrFile) { $stderrText = Get-Content $stderrFile -Raw }
        if (Test-Path $stdoutFile) { $stdoutText = Get-Content $stdoutFile -Raw }
        throw "NDEX_Frame.exe --smoke-export failed ($LASTEXITCODE). stderr=$stderrText stdout=$stdoutText"
    }

    @"
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

stdout_path = Path(sys.argv[1])
source = Path(sys.argv[2])
expected_hash = sys.argv[3]
text = stdout_path.read_text(encoding="utf-8", errors="replace")
line = next((row.strip() for row in text.splitlines() if row.strip().startswith("{")), "")
if not line:
    raise SystemExit("packaged smoke did not print a JSON result line")
payload = json.loads(line)
if payload.get("exported") != 1:
    raise SystemExit(f"expected exactly one export, got {payload!r}")
destination = Path(payload["items"][0]["destination"])
actual_hash = hashlib.sha256(source.read_bytes()).hexdigest().upper()
if actual_hash != expected_hash.upper():
    raise SystemExit("source SHA256 hash changed")
with Image.open(destination) as image:
    if image.size != (1080, 1440):
        raise SystemExit(f"expected 1080x1440, got {image.size}")
    if image.format != "JPEG":
        raise SystemExit(f"expected JPEG, got {image.format}")
    if not image.info.get("icc_profile"):
        raise SystemExit("output is missing icc profile")
    exif = image.getexif()
    if exif.get(33432) != "NDEX Frame copyright":
        raise SystemExit(f"copyright was not retained: {exif.get(33432)!r}")
    if 34853 in exif:
        raise SystemExit("GPS metadata was not removed")
print("packaged smoke ok", destination)
"@ | Set-Content -Path $verifyScript -Encoding UTF8

    python $verifyScript $stdoutFile $source $hashBefore
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged smoke verification failed"
    }
    Write-Host "Packaged smoke passed"
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
