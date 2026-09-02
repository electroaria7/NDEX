# NDEX Frame

type: program-note
status: usable
updated: 2026-09-02

## Purpose

NDEX Frame은 NDEX 시리즈의 네 번째 프로그램이다. 보정이 끝난 master 이미지를 **크롭 없이** Instagram 비율 캔버스 위에 배치하고, 지정한 출력 프로필로 내보낸다. 원본을 잘라내지 않고 여백을 채우는 것이 핵심이다.

다른 앱과 달리 Tkinter가 아니라 PySide6(Qt)로 만들었다.

## Core Workflow

1. master 파일 또는 폴더를 연다. Image Manager에서 넘어온 select handoff를 받을 수도 있다.
2. 프레임 preset(비율, 배경색)을 고른다.
3. 사진 크기와 위치를 조정한다.
4. 출력 폴더와 출력 프로필을 정한다.
5. Export All 또는 선택 항목만 export.

## Presets

- 비율 preset: Instagram 피드/스토리 등 고정 비율.
- 배경색 swatch와 Custom… 색 선택.
- 사진 크기 preset (예: 80% / 90% / 95%).
- 출력 프로필: 크기 규칙, 포맷, 품질, chroma subsampling, 색 공간, 메타데이터 정책.

미리보기는 실제 export plan을 그대로 투영한다. 화면에서 본 배치가 결과와 같다.

## Handoff

```powershell
NDEX_Frame.exe --open --handoff "%LOCALAPPDATA%\NDEX\manifests\select_handoff-20260902T101500Z.json"
NDEX_Frame.exe --open --source "D:\Masters" --output "D:\Framed"
```

- `--handoff`는 Image Manager의 pick 목록을 가져온다. JPG/PNG/TIFF만 들어온다. Frame은 RAW를 열지 않는다.
- `--output`은 내보내기 폴더를 미리 채운다.
- handoff와 `--source`가 같이 오면 handoff가 이긴다.
- 사용자가 GUI에서 파일이나 폴더를 새로 열면 handoff는 해제된다. 이후 session에는 새 폴더가 기록된다.

자세한 규칙은 [[Architecture/Sessions and Manifests]] 참고.

## Export Records

export가 끝나면 `export` manifest가 기록된다. 파일별 `exported` / `skipped` / `failed` 상태와 사용한 frame preset, output profile이 들어간다.

툴바의 **Job Results**로 그 기록을 다시 볼 수 있다. Tk 앱들과 달리 Frame은 Qt 전용 창을 쓴다.

실패한 export는 같은 창의 **Retry Failed**로 다시 돌린다. Frame은 그 파일들만 열고, 그 job의 출력 폴더를 되살린 뒤, 지금 설정된 frame/output preset으로 내보낸다. 이미 열려 있는 파일이면 다시 읽지 않는다. [[Architecture/Job Results]] 참고.

## Project Location

```text
ndex_frame
```

## Entry Points

```text
ndex_frame\main.py
ndex_frame\ui\main_window.py
ndex_frame\ui\workspace.py
ndex_frame\core\geometry.py
ndex_frame\services\export_job.py
```

## Run

```powershell
python -m ndex_frame.main
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\ndex_frame\build_package.ps1
```

## Output

```text
ndex_frame\dist\NDEX_Frame.exe
```

## Tests

```powershell
python -m unittest discover -s ndex_frame\tests -v
```

Qt 테스트는 `QT_QPA_PLATFORM=offscreen`으로 돌아간다.

## Current Test Focus

- render plan과 미리보기 투영이 정확히 일치하는지.
- export 충돌 정책 (rename / skip).
- handoff 가져오기와 handoff 해제.
- 패키징된 EXE의 smoke export.
