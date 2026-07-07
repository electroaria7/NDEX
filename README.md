# NDEX — Photo Workflow Suite

사진 작업 흐름(백업 → 선별 → 원본 추출)을 위한 Windows 데스크톱 유틸리티 시리즈.
각 앱은 독립 실행 가능하며, XMP 사이드카를 공용 데이터 계약으로 사용해 어도비 스타일로 느슨하게 연동됩니다 (Lightroom / Evoto 호환).

## 구성 앱

| 앱 | 역할 |
| --- | --- |
| **NDEX Launcher** | 워크플로 허브 — 3단계 대시보드, 최근 세션 이어가기, 개별 앱 실행 |
| **NDEX One** | 카메라/SD 카드 → 날짜 구조 백업. 원자적 복사, size/SHA-256 검증, 해시 기반 중복 스킵 |
| **NDEX Image Manager** | JPG/RAW 페어 브라우징, Pick/별점, 셀렉 백업, XMP export |
| **NDEX Auto Selector** | 셀렉 JPG로 RAW 원본 매칭·복제 + XMP 표시 (JPG 별점 승계 지원) |

지원 RAW: CR3 · CR2 · ARW · SRF · SR2 · NEF · NRW
파일명 매칭: Canon `IMG_0001` · Nikon `DSC_0001`/`_DSC0001` · Sony `DSC00001` (리네임된 파일도 토큰 추출 매칭)

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
```

## 빌드

요구사항: Windows, Python 3.10+, `pip install pyinstaller pillow`

```powershell
# 전체 릴리스 빌드 (EXE 4개 + release 폴더 조립)
powershell -ExecutionPolicy Bypass -File .\build_all.ps1
# 또는 run_build.cmd 더블클릭
```

결과: `release\NDEX_v{버전}\` — EXE 4개는 반드시 같은 폴더에 유지 (앱 간 핸드오프가 옆 폴더에서 실행파일을 찾음). 무설치 포터블.

개발 실행:

```powershell
python -m ndex_launcher.main        # 런처
python main.py                      # NDEX One
python -m dsb_image_manager.main    # Image Manager
python -m ndex_auto_selector.main   # Auto Selector
```

## 테스트

```powershell
python -m unittest discover -s tests                                  # NDEX One + 공통 설정 (15)
python -m unittest dsb_image_manager.tests.test_image_manager_services dsb_image_manager.tests.test_xmp_export  # (8)
python -m unittest discover -s ndex_auto_selector/tests               # (14)
python -m unittest ndex_launcher.tests.test_state                     # (3)
```

## 구조

```
ndex_common/          공유 모듈 — xmp(사이드카) · rating(JPG 별점 리더) · launch(핸드오프) · settings(공통 설정) · branding · version
src/ + main.py        NDEX One
dsb_image_manager/    NDEX Image Manager
ndex_auto_selector/   NDEX Auto Selector
ndex_launcher/        NDEX Launcher
build/, *_package.ps1 PyInstaller 빌드 (build_all.ps1 = 통합)
vendor/exiftool/      ExifTool (CR3 메타데이터·프리뷰 추출)
```

공통 설정: `%LOCALAPPDATA%\NDEX\config\settings.json` — 앱별 섹션, 병합 저장(다른 앱 설정 보존).

## 라이선스 고지

`vendor/exiftool`의 ExifTool은 Phil Harvey의 별도 라이선스(Perl Artistic/GPL)를 따릅니다.
