# NDEX Index

created: 2026-05-25
updated: 2026-10-11
type: project-index
status: active

## Overview

NDEX는 사진 작업 흐름을 중심으로 만든 로컬 데스크톱 유틸리티 시리즈다. 백업 정리, 이미지 선별/관리, 셀렉 JPG 기반 CR3 원본 추출, 크롭 없는 Instagram 내보내기를 각각 담당하는 4개 프로그램과, 이들을 순서대로 실행하는 런처 1개로 구성된다.

최신 공개 배포와 코드 버전은 0.9.5 Beta이며, 개발은 `release/0.9.6 @ c8c1d34`에서 진행 중이다. 0.9.6은 미배포다.
현재 누락 사항·CI 실패·미병합 작업과 실행 순서는 [[15_0.9.6_검수_추가작업_2026-10-11]]을 기준으로 한다.
0.9.5의 552개 회귀 검사와 패키지 검증은 과거 릴리스 기록이며 현재 개발본 검증과 구별한다. 상세: [[14_0.9.5_UIUX_패치노트_2026-10-10]].

## Program Notes

- [[Programs/NDEX One]]
- [[Programs/NDEX Image Manager]]
- [[Programs/NDEX Auto Selector]]
- [[Programs/NDEX Frame]]
- [[Programs/NDEX Launcher]]

## Project Notes

- [[15_0.9.6_검수_추가작업_2026-10-11]] — 현재 검수 결과, 누락 작업, 완료 기준, 로그
- [[14_0.9.5_UIUX_패치노트_2026-10-10]] — 최신 UI·UX 개선, 검수 수정 4건과 0.9.5 빌드·검증
- [[13_0.9.4_베타_배포_2026-10-10]] — 0.9.4 베타 배포 파일·검증·한계
- [[12_UIUX_효율_안정성_패치노트_2026-10-10]] — 0.9.4에 포함한 소스 개선 기록
- [[01 Development Progress]]
- [[02 Program Map]]
- [[Architecture/Shared Assets and Build]]
- [[Architecture/Sessions and Manifests]]
- [[Architecture/Job Results]]
- [[Roadmap]]

## Current Program Lineup

| Program | Role | Current State |
| --- | --- | --- |
| NDEX Launcher | 4단계 workflow 진입점, 마지막 작업 이어하기 | GUI, 0.9.5 EXE 재빌드 완료 |
| NDEX One | SD 카드/카메라 폴더 백업 정리 | GUI, CLI, 0.9.5 one-file EXE 재빌드 완료 |
| NDEX Image Manager | JPG/RAW 브라우징, 선별, 백업, XMP export | GUI, CLI, 0.9.5 one-file EXE 재빌드 완료 |
| NDEX Auto Selector | 셀렉 JPG 기준 RAW 원본 복제 및 XMP 표시 | GUI, CLI, 0.9.5 one-file EXE 재빌드 완료 |
| NDEX Frame | 크롭 없는 Instagram 캔버스 배치와 export | GUI (PySide6), 0.9.5 EXE 재빌드 완료 |

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
