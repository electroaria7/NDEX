# Job Results

type: architecture-note
updated: 2026-09-02
status: shipped in phase 3, retry added in phase 4

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

두 창 모두 manifest를 고쳐 쓰지 않는다. 할 수 있는 것:

- 실패 항목 재실행 (아래).
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

## Retry

```text
ndex_common\retry.py
```

`plan_retry(report)`가 job의 문제 경로를 둘로 나눈다.

| 필드 | 내용 |
| --- | --- |
| `paths` | 아직 그 자리에 있는 파일. 다시 돌릴 대상 |
| `missing` | 그 사이 옮겨졌거나 지워진 파일. 제외 대상 |
| `ready` | `paths`가 하나라도 있는가 |
| `summary` | 확인 창에 그대로 나가는 한 줄 |
| `context()` | 새 manifest에 넣을 `retry_of` 표시 |

manifest는 과거의 기록이고 사진은 그 뒤로 움직인다. 그래서 재실행은 항상 **지금 디스크에 있는지**부터 확인한다.

재실행할 수 있는 조합은 셋뿐이다 (`RETRYABLE`). select handoff는 작업이 아니라 포인터라서 다시 돌릴 것이 없다.

| App | Type | 재실행이 하는 일 |
| --- | --- | --- |
| NDEX One | backup | 그 파일들의 ScanItem을 다시 만들어 같은 백업 루트로 복사 |
| Auto Selector | extract | 두 폴더를 **다시 분석**한 뒤 해당 JPG만 복제 |
| NDEX Frame | export | 그 파일만 열고, 그 job의 출력 폴더로 다시 내보내기 |

Auto Selector가 다시 분석하는 것이 핵심이다. `missing`이나 `ambiguous`였던 항목은 사용자가 그 사이 RAW를 찾아 넣었거나 중복을 정리했기 때문에 다시 도는 것이고, 예전 매칭 결과를 재사용하면 같은 실패를 반복한다.

### 어떤 값을 쓰는가

- **폴더**는 그 job의 manifest에서 온다. 창에 떠 있는 폴더가 그때와 다를 수 있다.
- **설정**(중복 정책, 검증 방식, frame/output preset)은 지금 앱에 있는 값을 쓴다. 실패를 고치려고 설정을 바꿨을 수 있고, 그게 보통 재실행하는 이유다.
- 확인 창이 두 가지를 모두 말한 뒤에 시작한다.

### 재실행의 기록

재실행도 하나의 job이므로 자기 manifest를 남긴다. `context`에 `retry_of`(원래 manifest 경로), `retry_of_created_at`, `retried`(대상 파일 수)가 들어간다. 재실행의 재실행은 바로 앞 job을 가리킨다.

### Launcher

Launcher의 Job Results에는 Retry 버튼이 없다. 네 앱의 job을 다 보여주지만 실행기는 하나도 갖고 있지 않기 때문이다. 대신 문제 경로를 복사할 때 어느 앱을 열어야 하는지 알려준다.

## 백업의 파일별 기록

Phase 3까지 `BackupResult`에는 파일별 항목이 없었다. 백업 manifest의 `items`는 로그 메시지 몇 줄이었고 `path`가 비어 있었다. 그래서 Job Results에서 백업만 실패 경로를 낼 수 없었다.

Phase 4에서 `execute_backup`이 도달한 파일마다 `{path, status, detail, destination}`을 남긴다. `path`는 **원본 경로**다. 다시 복사할 대상이고, 대상 파일이 아예 만들어지지 않았을 때도 의미가 있는 유일한 값이다.

취소된 백업은 처리하지 못한 파일을 기록하지 않는다. 일어나지 않은 일이기 때문이다.

## Tests

```powershell
python -m unittest tests.test_report
python -m unittest tests.test_report_dialog
python -m unittest tests.test_retry
python -m unittest tests.test_ndex_one_retry
python -m unittest tests.test_backup_executor
python -m unittest ndex_frame.tests.test_report_dialog
python -m unittest discover -s ndex_auto_selector\tests
```

Tk 테스트는 인터프리터를 명시적으로 정리한다. 그냥 두면 나중 테스트의 워커 스레드가 파이널라이즈하면서 Tcl이 프로세스를 죽인다.
