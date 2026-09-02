# NDEX Launcher

type: program-note
status: usable
updated: 2026-09-02

## Purpose

NDEX Launcher는 4단계 workflow의 진입점이다. 각 단계를 카드로 보여주고, 마지막 작업 맥락을 읽어 이어서 열거나 빈 상태로 열게 한다.

## Workflow Cards

| Card | App | Description |
| --- | --- | --- |
| 01 Backup | NDEX One | 카메라/SD 파일을 날짜 기반 라이브러리로 복사 |
| 02 Select & Rate | Image Manager | 페어 브라우징, pick, rating, XMP export |
| 03 Extract | Auto Selector | 셀렉 JPG를 RAW master에 매칭하고 XMP 작성 |
| 04 Frame & Export | NDEX Frame | 크롭 없는 캔버스에 배치해 Instagram용으로 내보내기 |

## Continue and Open Empty

카드마다 상태 문구가 하나 붙는다.

```text
No previous session
Last: D:\Backup\2026-09-01
Last folder missing: Z:\Gone
Last handoff: ...\manifests\select_handoff-20260902T101500Z.json
```

- 이어갈 게 있으면 버튼은 **Continue**, 없으면 **Open**이다.
- Continue가 있을 때만 **Open Empty**가 함께 나온다. Open Empty는 `--open`만 넘기므로 앱은 기억된 폴더 없이 시작한다.
- 사라진 폴더는 인자에서 빠진다. 전부 빠지면 Continue는 Open Empty와 같아진다.
- Frame은 유효한 select handoff가 있으면 폴더보다 handoff를 먼저 쓴다.

규칙 전체는 [[Architecture/Sessions and Manifests]]에 있다.

## Job Results

푸터의 **Job Results...** 버튼은 4개 앱의 최근 job 결과를 한 창에 모아 보여준다. 카드마다도 해당 앱의 마지막 job 한 줄이 상태 문구 아래에 붙는다.

여기에는 **Retry Failed** 대신 **Retry in {앱}...** 이 있다. Launcher는 실행기가 없으니, 그 job을 실행한 앱을 `--open --retry <manifest>`로 띄워 그 앱의 Job Results를 그 job에서 열어 준다. 재실행 버튼은 거기서 누른다. [[Architecture/Job Results]] 참고.

## App Lookup

```text
ndex_common\launch.py
```

- 패키징 상태에서는 exe 폴더와 `Apps\`에서 찾는다.
- 소스 실행에서는 각 프로그램의 `dist` 폴더를 보고, 없으면 모듈로 실행한다.
- 옛 이름 `NDEX_One_OneFile.exe`도 계속 받아준다.

앱을 못 찾으면 "Build or install it first" 오류를 보여준다.

## Project Location

```text
ndex_launcher
```

## Entry Points

```text
ndex_launcher\main.py
ndex_launcher\state.py
```

## Run

```powershell
python -m ndex_launcher.main
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\ndex_launcher\build_package.ps1
```

## Output

```text
ndex_launcher\dist\NDEX_Launcher.exe
```

## Tests

```powershell
python -m unittest discover -s ndex_launcher\tests -v
```

## Current Test Focus

- 빈 설정에서 4개 카드가 모두 Open으로 나오는지.
- legacy 설정 키에서 Continue 인자를 만드는지.
- 사라진 폴더와 오래된 handoff가 Open Empty로 떨어지는지.
- 상태 문구가 실제 Continue 동작과 어긋나지 않는지.
