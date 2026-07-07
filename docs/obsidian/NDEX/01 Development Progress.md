# Development Progress

updated: 2026-05-25
type: progress-note

## Summary

NDEX는 기존 DSB 백업 도구에서 출발해 사진 백업/선별/원본 추출 workflow를 분리한 프로그램 시리즈로 확장되고 있다. 현재 개발은 3개 앱이 각자 독립 실행 가능한 구조를 갖는 방향으로 진행 중이다.

## Completed

- NDEX One
  - 카메라 폴더 또는 SD 카드 소스 분석.
  - RAW/JPG 파일 타입별 스캔.
  - 촬영 날짜 기반 백업 폴더 생성.
  - 중복 처리 정책 지원: rename, skip, overwrite.
  - 복제 검증 지원: size, sha256, none.
  - GUI/CLI 제공.
  - PyInstaller one-file EXE 빌드.

- NDEX Image Manager
  - 두 번째 NDEX 프로그램으로 독립 폴더 구성.
  - JPG/RAW 파일 스캔 및 페어 매칭.
  - 미리보기, 썸네일, EXIF 요약, pick/rating 상태 관리.
  - `.dsb_cache/catalog.sqlite` 기반 카탈로그.
  - Pick 파일 백업 기능.
  - GUI/CLI 및 EXE 빌드 구성.

- NDEX Auto Selector
  - 세 번째 NDEX 프로그램으로 독립 폴더 구성.
  - 셀렉 JPG 폴더와 원본 CR3 폴더를 매칭.
  - 매칭된 CR3를 작업용 폴더에 복제.
  - `IMG_0000` 패턴을 파일명 일부에서 추출해 매칭.
  - 셀렉 원본 표시용 `.xmp` 사이드카 생성.
  - XMP에 `xmp:Rating`, `xmp:Label`, `NDEX Selected` 키워드 기록.
  - GUI/CLI 및 one-file EXE 빌드 완료.

## Verified Test Coverage

```text
tests/test_backup_executor.py
tests/test_folder_manager.py
tests/test_scanner.py
dsb_image_manager/tests/test_image_manager_services.py
ndex_auto_selector/tests/test_auto_selector.py
```

## Recent Auto Selector Changes

- 파일명이 정확히 `IMG_0000.JPG`가 아니어도 매칭 가능.
- 예: `wedding_select_IMG_0345_final.JPG` -> `IMG_0345.CR3`.
- 복제 시 선택 표시용 XMP 생성 가능.
- GUI에서 XMP 생성 옵션과 별점 선택 제공.
- CLI 옵션 추가:

```powershell
--write-xmp --xmp-rating 5 --xmp-label "NDEX Selected"
```

## Current Direction

NDEX 시리즈는 기능별 단독 프로그램으로 유지하되, 공통 브랜딩/빌드/파일 타입 규칙은 재사용하는 구조가 적합하다. 이후에는 프로그램 간 데이터 흐름과 설정 공유를 더 정리할 수 있다.

