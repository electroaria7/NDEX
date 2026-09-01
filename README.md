# NDEX — Photo Workflow Suite

사진 작업 흐름(백업 → 선별 → 원본 추출 → 프레임·내보내기)을 위한 Windows 데스크톱 유틸리티 시리즈.
각 앱은 독립 실행 가능하며, XMP 사이드카와 공용 설정을 사용해 어도비 스타일로 느슨하게 연동됩니다 (Lightroom / Evoto 호환).

## 구성 앱

| 앱 | 역할 |
| --- | --- |
| **NDEX Launcher** | 워크플로 허브 — 4단계 대시보드, 최근 세션 이어가기, 개별 앱 실행 |
| **NDEX One** | 카메라/SD 카드 → 날짜 구조 백업. 원자적 복사, size/SHA-256 검증, 해시 기반 중복 스킵 |
| **NDEX Image Manager** | JPG/RAW 페어 브라우징, Pick/별점, 셀렉 백업, XMP export |
| **NDEX Auto Selector** | 셀렉 JPG로 RAW 원본 매칭·복제 + XMP 표시 (JPG 별점 승계 지원) |
| **NDEX Frame** | 완성된 Master를 자르지 않고 3:4 캔버스에 배치하고, 색 관리된 Instagram용 JPEG/PNG/WebP를 내보냄 |

지원 RAW: CR3 · CR2 · ARW · SRF · SR2 · NEF · NRW
파일명 매칭: Canon `IMG_0001` · Nikon `DSC_0001`/`_DSC0001` · Sony `DSC00001` (리네임된 파일도 토큰 추출 매칭)

NDEX Frame 입력: JPG/JPEG · PNG · TIFF. Master와 기존 출력은 덮어쓰지 않습니다. 자세한 사용법·변경점은 아래 **NDEX Frame**과 `ndex_frame/PATCH_NOTES.md`를 보세요.

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

완성된 Master를 자르지 않고(FIT) 캔버스에 올린 뒤, Output Profile로 JPEG/PNG/WebP를 만듭니다. Preview와 Export는 같은 배치 계산을 씁니다.

기본값: Frame Preset **White 3:4**, Output Profile **Instagram Feed HQ** (1080×1440 JPEG, Quality 95, 4:4:4, sRGB ICC). 두 프리셋은 서로 독립입니다.

### 오른쪽 Frame 패널

| 항목 | 동작 |
| --- | --- |
| **Ratio** | `3:4` · `4:5` · `1:1` 버튼, 또는 숫자 직접 입력. **불러온 전체 사진**에 바로 적용 |
| **Background** | White · Bright Gray · Medium Gray · Black 스와치, 또는 **Custom…** 색 선택. 전체 사진에 바로 적용 |
| **Photo Size** | 슬라이더, 또는 `80%` · `90%` · `95%`. **선택한 사진**에만 적용 |
| **Apply Current Framing to All** | 현재 비율·배경·크기·위치를 모든 사진에 복사 |

`Manage Presets` / `Save as Frame Preset`으로 저장한 프리셋은 그대로 둡니다. 메인 화면에서 먼저 맞춘 뒤 저장하면 됩니다.

### 내보내기

1. **Output Folder**를 고릅니다.
2. **Export Selected** 또는 **Export All**.
3. 하단 **진행 바**와 상태줄에 `파일이름 · 현재 / 전체`가 표시됩니다. **Cancel**로 중단합니다.

이미 있는 파일은 skip 또는 자동 rename만 합니다. Master는 수정하지 않습니다.

Frame 데이터: `%LOCALAPPDATA%\NDEX\Frame\`  
공통 설정 `frame` 섹션: `%LOCALAPPDATA%\NDEX\config\settings.json`

## 빌드

요구사항: Windows, Python 3.10+, `pip install -r requirements.txt` (Pillow, PySide6), PyInstaller 6.11.1

```powershell
# 전체 릴리스 빌드 (EXE 5개 + release 폴더 조립)
powershell -ExecutionPolicy Bypass -File .\build_all.ps1
# 또는 run_build.cmd 더블클릭
```

결과: `release\NDEX_v{버전}\` — EXE 5개는 반드시 같은 폴더에 유지 (앱 간 핸드오프가 옆 폴더에서 실행파일을 찾음). 무설치 포터블.

설치본(Inno Setup, ISCC 필요):

```powershell
powershell -ExecutionPolicy Bypass -File .\build_all.ps1 -Installer
```

결과: `release\NDEX_Setup_1.0.0.exe` — `C:\Program Files\NDEX`에 Launcher와 5개 앱을 설치하고, 시작 메뉴에 1–4단계 워크플로 바로가기를 만듭니다. 바탕화면 아이콘은 **NDEX Launcher**입니다.

개발 실행:

```powershell
python -m ndex_launcher.main        # 런처
python main.py                      # NDEX One
python -m dsb_image_manager.main    # Image Manager
python -m ndex_auto_selector.main   # Auto Selector
python -m ndex_frame                # Frame
```

## 테스트

```powershell
python -m unittest discover -s tests                                  # NDEX One + 공통 설정
python -m unittest discover -s dsb_image_manager\tests                # Image Manager
python -m unittest discover -s ndex_auto_selector\tests               # Auto Selector
python -m unittest discover -s ndex_launcher\tests                    # Launcher
python -m unittest discover -s ndex_frame\tests                       # Frame
powershell -ExecutionPolicy Bypass -File .\ndex_frame\tests\smoke_packaged.ps1  # 패키징된 NDEX_Frame.exe
```

## 구조

```
ndex_common/          공유 모듈 — xmp(사이드카) · rating(JPG 별점 리더) · launch(핸드오프) · settings(공통 설정) · branding · version
src/ + main.py        NDEX One
dsb_image_manager/    NDEX Image Manager
ndex_auto_selector/   NDEX Auto Selector
ndex_frame/           NDEX Frame (Qt-free core/imaging/services + PySide6 UI)
ndex_launcher/        NDEX Launcher
build/, *_package.ps1 PyInstaller 빌드 (build_all.ps1 = 통합)
vendor/exiftool/      ExifTool (CR3 메타데이터·프리뷰 추출)
```

공통 설정: `%LOCALAPPDATA%\NDEX\config\settings.json` — 앱별 섹션, 병합 저장(다른 앱 설정 보존). Frame 기본 프리셋 ID는 `frame` 섹션에 저장됩니다.

## 라이선스 고지

`vendor/exiftool`의 ExifTool은 Phil Harvey의 별도 라이선스(Perl Artistic/GPL)를 따릅니다.
Qt/PySide6, shiboken6, Pillow 고지는 `THIRD_PARTY_NOTICES.md`를 보세요.
