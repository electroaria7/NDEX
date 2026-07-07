# Shared Assets and Build

type: architecture-note
updated: 2026-05-25

## Shared Branding

공통 브랜딩 값은 `src/branding.py`에 있다.

```text
NDEX_ONE_TITLE = "NDEX One"
NDEX_IMAGE_MANAGER_TITLE = "NDEX Image Manager"
NDEX_AUTO_SELECTOR_TITLE = "NDEX Auto Selector"
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

## Dependencies

```text
Pillow>=10.0.0
PyInstaller
ExifTool optional but recommended
```

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
```

