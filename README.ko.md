# NDEX — 사진 워크플로 스위트

[English](README.md)

사진 작업 흐름(백업 → 선별 → 원본 추출 → 프레임·내보내기)을 위한 Windows 데스크톱 유틸리티입니다.
각 앱은 혼자 실행할 수 있고, XMP 사이드카와 공용 설정으로 느슨하게 연동됩니다 (Lightroom / Evoto 호환).

**공개 베타 (`0.9.1`).** GitHub 태그 `v1.0.0` / `v1.0.1`은 같은 줄에 안정 버전 번호를 붙인 기록입니다.

## 빠른 시작

**Windows 패키지 (권장)**

1. [Releases](https://github.com/electroaria7/NDEX/releases)에서 `NDEX_v0.9.1.zip`을 받습니다.
2. 압축을 풉니다. `Apps\` 폴더는 그대로 둡니다.
3. `NDEX_Launcher.exe`를 더블클릭합니다.
4. 카드 순서대로 진행합니다: **1. Backup** → **2. Select & Rate** → **3. Extract** → **4. Frame & Export**.

**설치본 (`NDEX_Setup_0.9.1.exe`)**

설치 프로그램이 있을 때:

1. 설치 프로그램을 실행합니다. 파일은 `C:\Program Files\NDEX`에 들어갑니다.
2. 시작 메뉴 또는 바탕화면의 **NDEX Launcher**를 엽니다.
3. 같은 네 장의 카드로 작업합니다.

이 GitHub `main` 브랜치는 **소스 코드**이며 설치 패키지가 아닙니다.

**소스에서 실행 (개발)**

```powershell
pip install -r requirements.txt
python -m ndex_launcher.main
```

one-file EXE는 처음 실행 시 압축 해제 때문에 몇 초 걸릴 수 있습니다.

## 구성 앱

| 앱 | 역할 |
| --- | --- |
| **NDEX Launcher** | 워크플로 허브 — 4단계 대시보드, 최근 세션 이어가기, 개별 앱 실행 |
| **NDEX One** | 카메라/SD 카드 → 날짜 구조 백업. 원자적 복사, size/SHA-256 검증, 해시 기반 중복 스킵 |
| **NDEX Image Manager** | JPG/RAW 페어 브라우징, Pick/별점, 셀렉 백업, XMP export |
| **NDEX Auto Selector** | 셀렉 JPG로 RAW 원본 매칭·복제 + XMP 표시 (JPG 별점 승계 지원) |
| **NDEX Frame** | 완성된 Master를 자르지 않고 캔버스에 배치하고, 색 관리된 Instagram용 JPEG/PNG/WebP를 내보냄 |

지원 RAW: CR3 · CR2 · ARW · SRF · SR2 · NEF · NRW  
파일명 매칭: Canon `IMG_0001` · Nikon `DSC_0001`/`_DSC0001` · Sony `DSC00001` (리네임된 파일도 토큰 추출 매칭)

NDEX Frame 입력: JPG/JPEG · PNG · TIFF. Master와 기존 출력은 덮어쓰지 않습니다.

## 워크플로

```
Camera/SD ─▶ NDEX One ─▶ 날짜 백업 라이브러리
                              │  "Open in Image Manager"
                              ▼
                    NDEX Image Manager ─▶ Pick/별점 ─▶ XMP export
                              │  "Send to Auto Selector"
                              ▼
                     NDEX Auto Selector ─▶ 작업폴더 (RAW + XMP)
                              ▼
                       Lightroom / Evoto
                              ▼
                          NDEX Frame ─▶ Instagram 배포본
```

## NDEX Frame

Preview와 Export는 같은 자르지 않는(FIT) 배치를 사용합니다. Frame Preset과 Output Profile은 서로 독립입니다.

기본값: Frame Preset **White 3:4**, Output Profile **Instagram Feed HQ** (1080×1440 JPEG, Quality 95, 4:4:4, sRGB ICC).

| 항목 | 동작 |
| --- | --- |
| **Ratio** | `3:4` · `4:5` · `1:1`, 또는 숫자 입력. **불러온 전체 사진**에 적용 |
| **Background** | White · Bright Gray · Medium Gray · Black 스와치, 또는 **Custom…**. 전체 사진 |
| **Photo Size** | 슬라이더 또는 `80%` · `90%` · `95%`. **선택한 사진**만 |
| **Apply Current Framing to All** | 현재 비율·배경·크기·위치를 모든 사진에 복사 |

**Output Folder**를 고른 뒤 **Export Selected** 또는 **Export All**. 진행 바에 `파일이름 · 현재 / 전체`가 표시됩니다. **Cancel**로 중단합니다. 이미 있는 파일은 skip 또는 자동 rename입니다.

Frame 데이터: `%LOCALAPPDATA%\NDEX\Frame\`  
공통 설정 `frame` 섹션: `%LOCALAPPDATA%\NDEX\config\settings.json`

## 패키지 구성 (설치본·포터블)

```
NDEX_v0.9.1\                  설치 위치: C:\Program Files\NDEX\
  NDEX_Launcher.exe           여기서 시작
  Apps\
    NDEX_One.exe
    NDEX_Image_Manager.exe
    NDEX_Auto_Selector.exe
    NDEX_Frame.exe
  Docs\
    README.md                 영어
    README.ko.md              이 파일 (한국어, 같은 내용)
    PATCH_NOTES.md
    FRAME_PATCH_NOTES.md
    LICENSE
    TERMS.md
    TERMS.ko.md
    THIRD_PARTY_NOTICES.md
    Licenses\
```

시작 메뉴 **NDEX**에 1–4단계 바로가기와 Launcher가 있습니다. 변경점: [PATCH_NOTES.md](PATCH_NOTES.md).

## 빌드

Windows, Python 3.10+, `pip install -r requirements.txt` (Pillow, PySide6), PyInstaller 6.11.1. 설치본은 Inno Setup (`ISCC`)이 필요합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\build_all.ps1
powershell -ExecutionPolicy Bypass -File .\build_all.ps1 -Installer
```

결과: `release\NDEX_v0.9.1\` (포터블)과 `release\NDEX_Setup_0.9.1.exe`.

```powershell
python -m ndex_launcher.main
python main.py
python -m dsb_image_manager.main
python -m ndex_auto_selector.main
python -m ndex_frame
```

## 테스트

```powershell
python -m unittest discover -s tests
python -m unittest discover -s dsb_image_manager\tests
python -m unittest discover -s ndex_auto_selector\tests
python -m unittest discover -s ndex_launcher\tests
python -m unittest discover -s ndex_frame\tests
powershell -ExecutionPolicy Bypass -File .\ndex_frame\tests\smoke_packaged.ps1
```

## 저장소 구조

```
ndex_common/          공유 모듈 — xmp · rating · launch · settings · branding · version
src/ + main.py        NDEX One
dsb_image_manager/    NDEX Image Manager
ndex_auto_selector/   NDEX Auto Selector
ndex_frame/           NDEX Frame
ndex_launcher/        NDEX Launcher
build/, *_package.ps1 PyInstaller / Inno Setup
vendor/exiftool/      ExifTool (CR3 메타데이터·프리뷰)
```

## 라이선스와 사용자 약관

NDEX는 [MIT License](LICENSE)의 무료 오픈소스입니다. 설치하거나 실행하면 [사용자 약관](TERMS.ko.md) ([English](TERMS.md))에 동의한 것으로 봅니다.

사진은 사용자 컴퓨터에 남습니다. 보증은 없습니다. Qt/PySide6, Pillow, ExifTool은 각자 라이선스를 따르며 `THIRD_PARTY_NOTICES.md`를 보세요.
