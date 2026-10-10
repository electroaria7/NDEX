# NDEX — 사진 워크플로 스위트

[English](README.md)

**공개 베타 · 0.9.4**

사진 작업 흐름(백업 → 선별 → 원본 추출 → 프레임·내보내기)을 위한 Windows 데스크톱 유틸리티입니다.
각 앱은 혼자 실행할 수 있고, XMP 사이드카와 공용 설정으로 연동됩니다. Lightroom / Evoto에서의 실제 XMP 해석은 별도 검증이 필요합니다.

지금은 **공개 베타**이며 1.0 안정판이 아닙니다. EXE는 코드 서명이 없어서 Windows SmartScreen이 경고할 수 있습니다. 안정 릴리스 전에 더 바뀔 수 있습니다.

## 공개 베타

- 현재 버전: **0.9.4 Beta**. 패키지: `NDEX_v0.9.4.zip` (포터블), `NDEX_Setup_0.9.4.exe` (설치본). [0.9.4 Beta 릴리스](https://github.com/electroaria7/NDEX/releases/tag/v0.9.4)에서 확인하세요.
- GitHub 태그 `v1.0.0` / `v1.0.1`은 같은 베타 줄에 안정 버전 번호를 붙인 기록입니다. `v0.9.3`을 포함한 과거 다운로드는 0.9.4 릴리스와 별도로 유지합니다.
- 이미 `NDEX_Setup_1.0.1.exe`를 설치했다면 `0.9.4`를 설치하기 전에 제거하세요. Windows는 `0.9.4`를 `1.0.1`보다 낮은 버전으로 봅니다.
- 변경점: [PATCH_NOTES.md](PATCH_NOTES.md).

## 빠른 시작

**0.9.4 주요 변경**

- Image Manager 백업·파일 내보내기·XMP 내보내기를 백그라운드에서 실행하고 진행률·취소를 제공합니다. 스캔과 파일 작업은 한 번에 하나씩 실행합니다.
- Auto Selector에 취소, 오래된 분석 방지, 번호가 붙은 동일 RAW 재사용을 추가했습니다. Image Manager에서 Pick한 JPG만 넘기며, 카메라 ID보다 정확히 같은 RAW 파일명을 우선합니다.
- One·Auto Selector·Frame은 취소한 미처리 파일을 Retry Failed 대상으로 남기고, Image Manager는 Job Results에 기록합니다. 네 작업 앱 모두 실행 중인 작업과 결과 처리가 끝난 뒤 닫힙니다.
- Frame은 디코딩한 미리보기를 재사용하고, 폴더 탐색은 제외할 백업·작업·캐시 디렉터리에 들어가지 않습니다. Image Manager 다중 선택 변경은 한 번의 데이터베이스 트랜잭션으로 처리합니다.
- 한글 RAW 경로의 촬영일, RAW/JPG 짝, 오래된 썸네일, XMP Pick 갱신, 설정 복구, Frame 색상·프로필 처리를 감사하여 수정했습니다.

취소는 현재 파일의 복사·검증·렌더링 또는 현재 메타데이터 묶음 처리가 끝난 뒤 적용합니다. One 분석 중 닫기를 요청하면 분석 완료를 기다립니다.
0.9.3의 검증 후 원자적 복사와 Auto Selector 중복 `skip`의 기존 RAW·XMP 보존 동작은 유지합니다.

실제 대량 RAW·SD카드 성능과 Lightroom/Evoto 호환성 확인은 후속 과제입니다.
검토 기록: [10월 9일 코드 감사](https://github.com/electroaria7/NDEX/blob/v0.9.4/docs/Improvement_Review_2026-10-09.md), [10월 10일 UI·작업 안정성](https://github.com/electroaria7/NDEX/blob/v0.9.4/docs/Improvement_Review_2026-10-10.md), [배포 검증](https://github.com/electroaria7/NDEX/blob/v0.9.4/docs/Release_Validation_2026-10-10.md).

실행 전 용량 요약·CSV/HTML 리포트·언어 통일·배포 자동화는 이후 순서입니다.
상세 계획은 [통합 로드맵](https://github.com/electroaria7/NDEX/blob/main/docs/obsidian/NDEX/Roadmap.md)을 참고하세요.

**Windows 패키지 (권장)**

1. [0.9.4 Beta 릴리스](https://github.com/electroaria7/NDEX/releases/tag/v0.9.4)에서 `NDEX_v0.9.4.zip`을 받습니다.
2. 압축을 풉니다. `Apps\` 폴더는 그대로 둡니다.
3. `NDEX_Launcher.exe`를 더블클릭합니다.
4. 카드 순서대로 진행합니다: **1. Backup** → **2. Select & Rate** → **3. Extract** → **4. Frame & Export**.

**설치본 (`NDEX_Setup_0.9.4.exe`)**

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
파일명 매칭: Canon `IMG_0001` · Nikon `DSC_0001`/`_DSC0001` · Sony `DSC00001`. 정확한 파일명을 우선하며, 이름을 바꾼 JPG 안의 카메라 ID는 그 ID로 시작하는 RAW와 매칭할 수 있습니다. RAW 앞에 다른 접두사가 있으면 정확한 파일명으로만 매칭합니다.

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
NDEX_v0.9.4\                  설치 위치: C:\Program Files\NDEX\
  NDEX_Launcher.exe           여기서 시작
  SHA256SUMS.txt
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

결과: `release\NDEX_v0.9.4\` (포터블)과 `release\NDEX_Setup_0.9.4.exe`.

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
