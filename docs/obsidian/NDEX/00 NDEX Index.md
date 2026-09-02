# NDEX Index

created: 2026-05-25
updated: 2026-09-02
type: project-index
status: active

## Overview

NDEX는 사진 작업 흐름을 중심으로 만든 로컬 데스크톱 유틸리티 시리즈다. 백업 정리, 이미지 선별/관리, 셀렉 JPG 기반 CR3 원본 추출, 크롭 없는 Instagram 내보내기를 각각 담당하는 4개 프로그램과, 이들을 순서대로 실행하는 런처 1개로 구성된다.

현재 버전은 `NDEX_VERSION = 0.9.1` (`NDEX_CHANNEL = "beta"`)이다. 공개 베타이며 1.0 제품이 아니다.

## Program Notes

- [[Programs/NDEX One]]
- [[Programs/NDEX Image Manager]]
- [[Programs/NDEX Auto Selector]]
- [[Programs/NDEX Frame]]
- [[Programs/NDEX Launcher]]

## Project Notes

- [[01 Development Progress]]
- [[02 Program Map]]
- [[Architecture/Shared Assets and Build]]
- [[Architecture/Sessions and Manifests]]
- [[Architecture/Job Results]]
- [[Roadmap]]

## Current Program Lineup

| Program | Role | Current State |
| --- | --- | --- |
| NDEX Launcher | 4단계 workflow 진입점, 마지막 작업 이어하기 | GUI, EXE 빌드 가능 |
| NDEX One | SD 카드/카메라 폴더 백업 정리 | GUI, CLI, one-file EXE 빌드 가능 |
| NDEX Image Manager | JPG/RAW 브라우징, 선별, 백업, XMP export | GUI, CLI, one-file EXE 빌드 가능 |
| NDEX Auto Selector | 셀렉 JPG 기준 CR3 원본 복제 및 XMP 표시 | GUI, CLI, one-file EXE 빌드 가능 |
| NDEX Frame | 크롭 없는 Instagram 캔버스 배치와 export | GUI (PySide6), EXE 빌드 가능 |

## Packaged Layout

```text
NDEX_Launcher.exe
Apps\NDEX_One.exe
Apps\NDEX_Image_Manager.exe
Apps\NDEX_Auto_Selector.exe
Apps\NDEX_Frame.exe
Docs\...
```

## Important Local Paths

```text
C:\Users\Owner\Documents\Projects\NDEX
C:\Users\Owner\Documents\Projects\NDEX\dist\NDEX_One_OneFile.exe
C:\Users\Owner\Documents\Projects\NDEX\dsb_image_manager\dist\NDEX_Image_Manager.exe
C:\Users\Owner\Documents\Projects\NDEX\ndex_auto_selector\dist\NDEX_Auto_Selector.exe
C:\Users\Owner\Documents\Projects\NDEX\ndex_frame\dist\NDEX_Frame.exe
C:\Users\Owner\Documents\Projects\NDEX\ndex_launcher\dist\NDEX_Launcher.exe
```

## Shared User Data

```text
%LOCALAPPDATA%\NDEX\config\settings.json
%LOCALAPPDATA%\NDEX\sessions\{app}.json
%LOCALAPPDATA%\NDEX\manifests\{type}-{stamp}.json
%LOCALAPPDATA%\NDEX\logs\
```
