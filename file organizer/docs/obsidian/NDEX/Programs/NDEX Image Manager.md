# NDEX Image Manager

type: program-note
status: usable
updated: 2026-05-25

## Purpose

NDEX Image Manager는 NDEX 시리즈의 두 번째 프로그램이다. JPG와 RAW 파일을 함께 탐색하고, 페어 매칭, 미리보기, 선별, 평점, 백업 흐름을 담당한다.

## Main Features

- JPG/RAW shooting folder 스캔.
- RAW/JPG 파일 페어 탐지.
- JPG 직접 미리보기와 썸네일 생성.
- RAW 내장 JPEG preview 추출 시도.
- EXIF 요약 표시.
- Pick, Maybe, Reject 등 선별 상태 관리.
- Rating 상태 관리.
- `.dsb_cache/catalog.sqlite` 기반 카탈로그.
- Pick 파일 백업 기능.

## Project Location

```text
dsb_image_manager
```

## Entry Points

```text
dsb_image_manager\main.py
dsb_image_manager\dsb_image_manager\ui\tk_app.py
dsb_image_manager\dsb_image_manager\services\scanner.py
dsb_image_manager\dsb_image_manager\services\backup.py
```

## Run

```powershell
python -m dsb_image_manager.main
```

## CLI Examples

```powershell
python -m dsb_image_manager.main --source "D:\Photos\Shoot" --scan
python -m dsb_image_manager.main --source "D:\Photos\Shoot" --backup-picked --backup-destination "E:\Photo Backup"
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\dsb_image_manager\build_package.ps1
```

## Output

```text
dsb_image_manager\dist\NDEX_Image_Manager.exe
```

## Notes

- 폴더명은 아직 `dsb_image_manager`지만 제품명은 `NDEX Image Manager`로 정리되어 있다.
- 추후 PySide6로 UI 교체 가능성을 열어둔 구조다.

