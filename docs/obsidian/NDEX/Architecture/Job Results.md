# Job Results

type: architecture-note
updated: 2026-09-02
status: shipped in phase 3

## Purpose

[[Sessions and Manifests]]가 끝난 job을 전부 JSON으로 남기지만, phase 2까지는 그 파일을 다시 읽는 곳이 없었다. 이 노트는 읽는 쪽이다.

사용자가 답을 얻어야 하는 질문은 하나다. **방금 그 작업이 실제로 뭘 했나.** 몇 개가 복사됐고, 뭐가 빠졌고, 왜 빠졌나.

## Read Model

```text
ndex_common\report.py
```

- `read_report(path)` — manifest 하나를 `JobReport`로 파싱한다. 읽을 수 없으면 `None`.
- `recent_reports(apps=..., types=..., limit=...)` — manifest 폴더를 훑어 최신순으로 준다. `latest-*` 포인터 파일은 건너뛴다. `limit=0`이면 전부.
- `latest_report(app, type)` — `latest-{app}-{type}.json` 포인터를 읽는다.

`JobReport`가 UI에 주는 것:

| 속성 | 내용 |
| --- | --- |
| `headline` | `Backup - 2026-09-02 10:15 - 42 copied, 1 failed` |
| `count_summary` | 0이 아닌 카운트만, 읽는 순서대로 |
| `display_time` | UTC 기록을 로컬 시간으로. 파싱 실패하면 원문 그대로 |
| `items_by_status()` | 상태별로 묶되 문제 상태를 먼저 |
| `problem_paths()` | `failed` / `error` / `ambiguous` / `missing` 경로 목록 |
| `failed_count` | 기록된 카운트, 없으면 문제 항목 개수 |
| `cancelled` | context의 취소 표시 |

문제 상태는 `PROBLEM_STATUSES`에 있다. 여기에 들어간 항목은 목록 위로 올라가고, 목록 행이 빨간색으로 표시된다.

## Windows

Tk 앱 4개는 창 하나를 공유한다.

```text
ndex_common\report_dialog.py     # NDEX One, Image Manager, Auto Selector, Launcher
ndex_frame\ui\report_dialog.py   # NDEX Frame (Qt)
```

왼쪽은 최근 job 목록, 오른쪽은 선택한 job의 파일별 내역이다.

두 창 모두 읽기 전용이다. manifest도 사진도 건드리지 않는다. 할 수 있는 것:

- 문제 경로를 클립보드로 복사.
- source / destination / manifest 폴더 열기. 폴더가 없으면 버튼이 비활성이다.

## Where It Opens

| App | 위치 | 범위 |
| --- | --- | --- |
| NDEX Launcher | 푸터 **Job Results...** | 4개 앱 전부 |
| NDEX One | 버튼 행 **Job Results...** | `ndex_one` |
| Image Manager | **File > Job Results...** | `image_manager` |
| Auto Selector | 버튼 행 **작업 결과...** | `auto_selector` |
| NDEX Frame | 툴바 **Job Results** | `frame` |

Launcher 카드에는 창을 열지 않아도 보이도록 해당 앱의 마지막 job 한 줄이 붙는다 (`StepState.result_text`).

기록된 job이 하나도 없으면 창 대신 안내 메시지가 뜬다.

## Not In This Phase

실패 항목 **재실행**은 없다. 지금은 문제 경로를 복사해 주고, 같은 폴더로 job을 다시 돌리라고 안내한다.

제대로 만들려면 backup / extract / export 실행기가 각각 "이 파일 목록만" 처리하는 부분 재개를 받아야 하고, 그 사이 원본이 움직였을 때의 처리도 정해야 한다. [[Roadmap]]의 phase 4 후보에 있다.

## Tests

```powershell
python -m unittest tests.test_report
python -m unittest tests.test_report_dialog
python -m unittest ndex_frame.tests.test_report_dialog
python -m unittest discover -s ndex_launcher\tests
```

Tk 테스트는 인터프리터를 명시적으로 정리한다. 그냥 두면 나중 테스트의 워커 스레드가 파이널라이즈하면서 Tcl이 프로세스를 죽인다.
