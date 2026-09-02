# Shared Assets and Build

type: architecture-note
updated: 2026-09-02

## Shared Branding

공통 브랜딩 값은 `ndex_common/branding.py`에 있다. `src/branding.py`는 이를 재수출한다.

```text
NDEX_ONE_TITLE = "NDEX One"
NDEX_IMAGE_MANAGER_TITLE = "NDEX Image Manager"
NDEX_AUTO_SELECTOR_TITLE = "NDEX Auto Selector"
NDEX_LAUNCHER_TITLE = "NDEX Launcher"
NDEX_FRAME_TITLE = "NDEX Frame"
```

버전 값도 같은 모듈에 있다.

```text
NDEX_VERSION = "0.9.1"
NDEX_CHANNEL = "beta"
```

공통 자산 경로:

```text
assets\branding
assets\branding\ndex_icon.ico
assets\branding\ndex_icon_32.png
assets\branding\ndex_icon_64.png
assets\branding\ndex_wordmark_header.png
```

## Build Tools

PyInstaller 관련 도구는 `.build_tools` 아래에 있다. 각 프로그램은 자체 빌드 스크립트를 갖는다.

| Program | Build Script | Output |
| --- | --- | --- |
| NDEX One | `build\build.ps1 -OneFile` | `dist\NDEX_One_OneFile.exe` |
| NDEX Image Manager | `dsb_image_manager\build_package.ps1` | `dsb_image_manager\dist\NDEX_Image_Manager.exe` |
| NDEX Auto Selector | `ndex_auto_selector\build_package.ps1` | `ndex_auto_selector\dist\NDEX_Auto_Selector.exe` |
| NDEX Frame | `ndex_frame\build_package.ps1` | `ndex_frame\dist\NDEX_Frame.exe` |
| NDEX Launcher | `ndex_launcher\build_package.ps1` | `ndex_launcher\dist\NDEX_Launcher.exe` |

전체를 한 번에 빌드하려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_all.ps1
powershell -ExecutionPolicy Bypass -File .\build_all.ps1 -Installer
```

`build_all.ps1`은 git 태그와 `NDEX_VERSION`이 다르면 실패하고, 릴리스 폴더에 `SHA256SUMS.txt`를 만든다. Inno Setup 설치 파일은 `ISCC`가 설치되어 있을 때만 생성된다.

## Dependencies

```text
Pillow>=12.3.0
PySide6            # NDEX Frame only
PyInstaller
ExifTool optional but recommended
```

고정 버전은 `requirements.lock`에 있다. CI는 이 파일로 설치한다.

## ExifTool

ExifTool은 CR3 메타데이터 추출과 RAW preview 추출에서 중요하다. 패키징 시 다음 위치를 사용한다.

```text
vendor\exiftool\exiftool.exe
vendor\exiftool\exiftool_files\...
```

## Testing Commands

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s dsb_image_manager\tests -v
python -m unittest discover -s ndex_auto_selector\tests -v
python -m unittest discover -s ndex_launcher\tests -v
python -m unittest discover -s ndex_frame\tests -v
```

Windows CI는 Python 3.10과 3.12에서 이 다섯 묶음을 모두 돌린다.

## Shared User Data

설정과 세션, manifest, 로그는 앱이 공유한다. 구조는 [[Sessions and Manifests]]에 있다.

```text
%LOCALAPPDATA%\NDEX\config\settings.json
%LOCALAPPDATA%\NDEX\sessions\
%LOCALAPPDATA%\NDEX\manifests\
%LOCALAPPDATA%\NDEX\logs\
```

`settings.json` 쓰기는 잠금 후 reload/merge/atomic write다. 한 앱이 다른 앱의 설정 구역을 덮어쓰지 않는다.

