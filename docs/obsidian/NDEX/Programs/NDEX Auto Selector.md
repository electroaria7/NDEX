# NDEX Auto Selector

type: program-note
status: usable
updated: 2026-05-25

## Purpose

NDEX Auto Selector는 NDEX 시리즈의 세 번째 프로그램이다. 셀렉된 JPG 폴더를 기준으로 같은 촬영 번호의 CR3 원본을 찾아 작업용 폴더에 복제하고, 필요하면 XMP 사이드카를 생성해 셀렉 상태를 표시한다.

## Core Workflow

1. 원본 CR3 폴더 선택.
2. 셀렉 JPG 폴더 선택.
3. 작업용 폴더 선택.
4. 매칭 분석.
5. CR3 복제.
6. 선택 옵션에 따라 XMP 생성.

## Matching Rules

기본 매칭은 파일명 stem 기준이다.

```text
IMG_1024.JPG -> IMG_1024.CR3
```

파일명 앞뒤에 추가 정보가 있어도 `IMG_0000` 형태의 네 자리 번호를 추출해 매칭한다.

```text
album_pick_IMG_1024_edit.JPG -> IMG_1024.CR3
wedding_select_IMG_0345_final.JPG -> IMG_0345.CR3
```

## XMP Sidecar Behavior

CR3 파일 자체는 수정하지 않는다. 대신 복제된 CR3 옆에 같은 stem의 `.xmp` 파일을 생성한다.

```text
IMG_1024.CR3
IMG_1024.xmp
```

XMP에는 다음 표시가 들어간다.

```text
xmp:Rating="5"
xmp:Label="NDEX Selected"
keyword: NDEX Selected
```

## Project Location

```text
ndex_auto_selector
```

## Entry Points

```text
ndex_auto_selector\main.py
ndex_auto_selector\ndex_auto_selector\services\selector.py
ndex_auto_selector\ndex_auto_selector\ui\tk_app.py
```

## Run

```powershell
python -m ndex_auto_selector.main
```

## CLI Examples

```powershell
python -m ndex_auto_selector.main --raw-source "E:\DCIM" --selected-jpg "D:\Selects" --analyze
python -m ndex_auto_selector.main --raw-source "E:\DCIM" --selected-jpg "D:\Selects" --work-folder "D:\Work" --copy
python -m ndex_auto_selector.main --raw-source "E:\DCIM" --selected-jpg "D:\Selects" --work-folder "D:\Work" --copy --write-xmp --xmp-rating 5
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\ndex_auto_selector\build_package.ps1
```

## Output

```text
ndex_auto_selector\dist\NDEX_Auto_Selector.exe
```

## Tests

```powershell
python -m unittest discover -s ndex_auto_selector\tests -v
```

## Current Test Focus

- 대소문자 무시 JPG/CR3 매칭.
- 중복 파일 rename 처리.
- XMP 사이드카 생성.
- 파일명 중간의 `IMG_0000` 토큰 매칭.

