# Development Progress

updated: 2026-10-11
type: progress-note

## Summary

실행 체크리스트: [[15_0.9.6_검수_추가작업_2026-10-11]]. 근거: [검수 로그](../../logs/2026-10-11-release-0.9.6-review.log).

최신 공개 배포는 **0.9.5 Beta**, 현재 개발 기준은 **release/0.9.6 @ c8c1d34**다.
2026-10-11 원격 fetch 및 GitHub API로 확인했으며 로컬/원격 release 브랜치는 같다.
0.9.6은 미배포 상태이고 `ndex_common/version.py`는 아직 `0.9.5`다.

### 최신 버전과 통합 범위

| 구분 | 확인 결과 |
| --- | --- |
| 최신 공개 배포 | [v0.9.5 Beta](https://github.com/electroaria7/NDEX/releases/tag/v0.9.5), 2026-10-10 21:04:45 UTC 공개. ZIP·설치본·체크섬 제공 |
| GitHub Latest 표시 | v0.9.3. v0.9.4/0.9.5는 pre-release이므로 Latest API와 최신 공개 배포가 다름 |
| main | `4390ada`; release/0.9.6에는 main에 없는 커밋 22개가 있음 |
| 통합 개발 기준 | 로컬/원격 `release/0.9.6` 모두 `c8c1d34` |
| 별도 작업 중 | Manager worktree `8b540aa`와 미커밋 변경. 그리드·툴바·번역 후속 작업은 release에 미병합 |
| 과거 v1.0.0/v1.0.1 | 2026-09-01에 공개한 이전 번호이며 최신 배포가 아님 |

### 0.9.6에서 병합된 작업

| 작업 | 상태 / 남은 조건 |
| --- | --- |
| A1 공용 i18n·Launcher 언어 선택 | 병합. 실제 한국어 번역은 미완료 |
| A2 공용 RAW 형식·CRW·큰 내장 JPEG 선택·방향 처리 | 병합. 실제 Canon/Sony/Nikon 19샘플 검증 기록은 `docs/RAW_Compatibility.md` 참조 |
| A3 Manager RAW+JPG shot·Undo/Redo·점진 스캔·취소·빠른 재스캔 | 병합. 재스캔 뒤 Undo 결함 2개 확인 |
| C1 One·Selector·공용 결과/재시도 문자열 래핑 | 병합. 번역값 및 추출 도구 보완 필요 |
| B2 Frame 썸네일·프리셋 관리·결과 표·번역 연결 | 병합. 프리셋 관리 결함 2개 및 CI 실패 확인 |
| Manager 그리드·단일 행 툴바·번역 연결 후속 | 별도 worktree에서 진행 중. 커밋·미커밋 변경을 합쳐 검수 후 통합 필요 |

### 누락 및 후속 작업 목록

아래는 완료 판정 전에 처리할 항목이다. 검수로 발견했으며 이번 문서 갱신에서 코드를 수정하지 않았다.

- [ ] **CI 복구:** [현재 커밋 CI](https://github.com/electroaria7/NDEX/actions/runs/38159035172)는 Python 3.12 성공, 3.10 실패. Frame `test_keyboard_navigation_still_steps_through_photos` 종료 시 임시 폴더 정리에서 WinError 145 발생. 비동기 작업 종료/정리 순서를 조사하고 두 버전 모두 재검증.
- [ ] **Manager Undo:** 같은 폴더 재스캔 후 SQLite ID 재사용으로 다른 파일을 변경하는 문제, RAW 파트너 추가 후 Undo가 JPG만 복원하는 문제 수정 및 회귀 테스트 (`tk_app.py:1011,1202,1525`).
- [ ] **Frame 프리셋:** New가 현재 편집값 대신 저장본을 복사하는 문제와 명시적으로 적용한 동일 ID 프리셋이 관리 창 종료 후 이전 편집값으로 돌아오는 문제 수정 (`main_window.py:584,597`).
- [ ] **한국어 번역:** 통합 브랜치 `ko.json` 일반 키 583개 전부 빈 값. 언어 선택과 `_()` 래핑은 번역 완료를 의미하지 않음. Manager 미병합 키까지 확정한 뒤 번역·자리표시자·줄바꿈·화면 폭 검수.
- [ ] **번역 추출:** `tools/i18n_extract.py` 기본 대상에 실제 One 소스 `src` 추가. 현재 `--prune`은 사용 중인 일반 키 129개와 복수형 키 2개를 제거함(메모리상 검증). Windows cp949 출력의 UnicodeEncodeError도 처리.
- [ ] **미병합 작업 보존/통합:** Manager `8b540aa` 및 미커밋 backup/exporter/tk_app/ko.json, 미추적 `test_grid_view.py` 확인. 커밋본 ko.json에는 현재 Manager 추출 기준 일반 키 211개·복수형 키 12개가 없고 미커밋 파일에만 반영돼 있으므로 커밋만 병합하지 말 것. 작업 중 스냅샷 테스트는 아래 별도 결과 참조.
- [ ] **Git 추적 정리:** `c8c1d34`가 worktree gitlink 두 개를 추가해 `git submodule status` 실패. 실제 작업 폴더를 보존하고 인덱스 추적/ignore만 정리.
- [ ] **릴리스 준비:** 0.9.6 버전·README·PATCH_NOTES 동기화, 5개 EXE·ZIP·설치본·체크섬 생성 및 패키지 GUI/한글 경로/고DPI/업그레이드 검증. 현재 버전으로 빌드하면 0.9.5 출력 경로를 사용함.
- [ ] **후속 범위:** CSV/HTML 결과 내보내기, 대량 RAW/SD 성능, 실제 세로 RAW 방향, Lightroom/Evoto XMP 해석, 태그 기반 배포 자동화. 0.9.6 필수 범위와 이후 범위를 확정할 것.

RAW 검증을 전부 미완료로 표시하지 않는다. 19샘플의 날짜·메타데이터·내장 JPEG·XMP 생성·매칭·백업 검증 기록이 있다.
실제 세로 RAW와 대량 성능, 외부 앱 XMP 해석은 남아 있다. RAW 원본 픽셀 디코딩은 현 설계에서 지원하지 않는다.
One DNG와 다른 브랜드 RAW 지원도 현재 제한이며, 자동으로 이번 릴리스 필수 요구로 간주하지 않는다.

NDEX는 기존 DSB 백업 도구에서 출발해 사진 백업/선별/원본 추출/내보내기 workflow를 분리한 프로그램 시리즈다. 각 앱은 독립 실행이 가능하고, [[Programs/NDEX Launcher]]가 4단계 순서를 묶는다.

2026-09-01 이후 개발은 phase 단위로 진행된다. 각 phase는 브랜치와 PR 하나에 대응한다.

## Phase Status

| Phase | Branch | PR | Theme | State |
| --- | --- | --- | --- | --- |
| 0 | `fix/phase-0-correctness` | #6 | 백업/사이드카/RAW 매칭 정확성 | merged |
| 1 | `fix/phase-1-foundation` | #7 | 설정 잠금, CI, 크래시 로그, 0.9.1 재태깅 | merged |
| 2 | `feat/phase-2-sessions` | #9 | 세션 문서, job manifest, 앱 간 handoff | merged + 후속 수정 |
| 3 | `feat/phase-3-job-results` | #10 | job 결과를 UI에서 읽기 | merged |
| 4 | `feat/phase-4-retry-failed` | #11 | 실패 항목 재실행 | merged |
| 5 | `feat/phase-5-launcher-retry` | - | Launcher에서 앱으로 넘기는 재실행 | 0.9.2 포함 |
| 6 | - | - | 통합 handoff 테스트와 기록 보관 정책 | 0.9.2 포함 |
| 7A | `fix/file-copy-safety` | - | 복사 안전성·백업 상태·skip XMP 보호 | 구현/회귀 검증 완료 |

### Phase 5 (2026-09-02)

Launcher는 실행기가 없으니 재실행을 그 앱에 넘긴다.

- Launcher Job Results의 **Retry in {앱}...** 이 `--open --retry <manifest>`로 그 앱을 띄운다.
- NDEX One / Auto Selector / Frame이 `--retry`를 받아 Job Results를 그 job에서 연다. 밀려난 manifest도 읽어 온다.
- 재실행은 여전히 그 앱의 Retry Failed로만 시작된다.

### Phase 4 (2026-09-02)

Phase 3이 보여준 실패 목록을 실제로 다시 돌린다. 자세한 내용은 [[Architecture/Job Results]]에 있다.

- Job Results 창의 **Retry Failed**. job을 실행하는 세 앱(NDEX One, Auto Selector, Frame)에만 붙는다.
- 폴더는 그 job의 manifest에서 온다. 설정은 지금 창에 떠 있는 값을 쓴다.
- 그 사이 사라진 파일은 세어서 제외하고, 전부 사라졌으면 재실행하지 않는다.
- 재실행 결과는 새 manifest로 남고 `context.retry_of`로 원래 job을 가리킨다.
- NDEX One이 백업의 파일별 결과를 기록하기 시작했다. 그전까지 백업 manifest에는 로그 메시지만 있어서 실패 경로를 목록에 낼 수도, 복사할 수도 없었다.
- extract manifest에 원본 RAW 폴더가 들어간다. 재실행이 다시 매칭하려면 필요하다.
- Launcher의 Job Results는 아무것도 실행하지 않는다. (Phase 5에서 앱으로 넘기게 했다.)

### Phase 3 (2026-09-02)

Phase 2가 남긴 manifest를 읽어 UI에 보여준다. 자세한 내용은 [[Roadmap]]에 있다.

- `ndex_common/report.py`가 manifest를 찾아 요약하고 상태별로 묶는다.
- **Job Results** 창에서 최근 job과 파일별 처리 결과를 본다. 문제 파일이 먼저 나온다.
- Launcher 카드마다 마지막 job 결과 한 줄이 붙는다.
- 실패 항목 재실행은 넣지 않고 문제 경로 복사까지만 제공했다. Phase 4에서 처리했다.

### Phase 2 후속 수정 (2026-09-02)

Phase 2는 PR #9로 병합되었으나, 이후 코드 리뷰에서 6건의 결함을 찾아 수정했다.

- Frame에서 파일/폴더를 새로 열면 이전 handoff를 지운다. 지우지 않으면 Launcher Continue가 오래된 select handoff를 다시 불러왔다.
- Continue는 handoff 파일의 존재만 보지 않고, manifest가 실제로 읽히고 나열된 파일이 남아 있는지까지 확인한다. 아니면 `--source` 폴더로 되돌아간다.
- Launcher 상태 문구가 유효한 handoff가 있는데도 "Last folder missing"을 보여주지 않는다.
- NDEX One의 **Open Empty**가 실제로 빈 상태로 열린다. 이전에는 `--open`만 받아도 settings의 마지막 폴더를 채웠다.
- Image Manager **Send Picks to Frame…**은 handoff 기록에 실패하면 오류를 보여주고 Frame을 열지 않는다.
- Manifest 파일명이 같은 초에 끝난 두 job끼리 서로 덮어쓰지 않는다.

## Completed

- NDEX One
  - 카메라 폴더 또는 SD 카드 소스 분석.
  - RAW/JPG 파일 타입별 스캔.
  - 촬영 날짜 기반 백업 폴더 생성.
  - 중복 처리 정책 지원: rename, skip, overwrite.
  - 복제 검증 지원: size, sha256, none.
  - 임시 파일에 쓰고 교체하는 atomic copy.
  - GUI/CLI 제공, PyInstaller one-file EXE 빌드.

- NDEX Image Manager
  - JPG/RAW 파일 스캔 및 페어 매칭.
  - 미리보기, 썸네일, EXIF 요약, pick/rating 상태 관리.
  - `.dsb_cache/catalog.sqlite` 기반 카탈로그.
  - Pick 파일 백업, XMP export (RAW는 `stem.xmp`, JPG는 `file.JPG.xmp`).
  - 폴더 스캔을 백그라운드 큐에서 처리해 UI가 멈추지 않음.
  - **Send Picks to Frame…**으로 select handoff 작성.
  - GUI/CLI 및 EXE 빌드 구성.

- NDEX Auto Selector
  - 셀렉 JPG 폴더와 원본 CR3 폴더를 매칭.
  - 매칭된 CR3를 작업용 폴더에 복제.
  - `IMG_0000` 패턴을 파일명 일부에서 추출해 매칭.
  - 모호한 RAW 매칭은 임의로 고르지 않고 보고.
  - 셀렉 원본 표시용 `.xmp` 사이드카 생성 (`xmp:Rating`, `xmp:Label`, `NDEX Selected`).
  - GUI/CLI 및 one-file EXE 빌드 완료.

- NDEX Frame
  - 크롭 없이 Instagram 비율 캔버스에 원본을 배치.
  - 비율/배경색/사진 크기 preset.
  - export 결과를 manifest로 기록.
  - `--handoff`로 Image Manager pick 목록을 가져오고 `--output`으로 내보내기 폴더를 미리 지정.

- NDEX Launcher
  - 4단계 workflow 카드 UI.
  - 마지막 작업 폴더와 handoff를 읽어 Continue / Open Empty 제공.
  - `Apps\` 폴더와 소스 실행 양쪽에서 앱을 찾음.

- 공통 기반
  - `settings.json` 갱신은 잠금 후 reload/merge/atomic write (`schema_version`).
  - 패키징된 앱은 `%LOCALAPPDATA%\NDEX\logs\`에 크래시 로그 기록.
  - Windows CI가 Python 3.10과 3.12에서 단위 테스트 실행.
  - 릴리스 폴더에 `SHA256SUMS.txt` 포함, 태그와 `NDEX_VERSION` 불일치 시 빌드 실패.
  - 4단계 workflow(백업 → 셀렉 넘기기 → 추출 → export)를 GUI 없이 끝까지 도는 통합 테스트.
  - job manifest 보관 정책: type별 최신 100개만 남기고, 세션이 가리키는 것은 남긴다.

## Verified Test Coverage

```powershell
python -m unittest discover -s tests                      # 283 (1 skipped)
python -m unittest discover -s dsb_image_manager\tests    # 74
python -m unittest discover -s ndex_auto_selector\tests   # 73
python -m unittest discover -s ndex_launcher\tests        # 27
python -m unittest discover -s ndex_frame\tests           # 226
```

2026-10-11 `c8c1d34` 로컬 Python 3.12.10 검수: 총 683개, 682개 통과·1개 건너뜀·실패 0개.
동일 커밋 원격 CI는 Python 3.12 성공, 3.10 실패이므로 전체 검증 완료가 아니다.
별도 Manager worktree와 미커밋 작업은 이 수치에 포함하지 않는다. 0.9.5의 552개와 Frame 중간 단계의 603개는 과거 기록이다.

별도 Manager worktree `8b540aa` + 미커밋 변경의 읽기 전용 검수 결과:

- Manager 전체 110개: 실패 4개·오류 3개(71.693초).
- 신규 그리드 테스트 단독 36개: 실패 4개·오류 2개(48.218초).
- 스크롤 인덱스 왕복/경계와 가상화 수량 검증, 자동 다음 사진 이동 후 평점 기대값, Tk 메뉴 tearoff 조회, 중복 destroy 및 Windows 썸네일 파일 정리가 실패에 포함된다.
- 구현과 테스트 기대값/정리 코드 문제가 섞여 있으므로 이를 모두 사용자 기능 결함으로 세지 않는다. 각 원인 분리 후 통합 전에 다시 검증한다.
- 전체 테스트는 결과 출력 후에도 프로세스가 남아 검수 에이전트가 자신이 시작한 테스트 프로세스만 종료했다. worker 종료/정리 검증을 추가한다. 그리드 단독 실행은 정상적으로 실패 종료했다.

## Current Direction

각 프로그램은 단독 실행 가능한 상태로 유지하되, 공통 브랜딩/빌드/설정/세션 규칙은 `ndex_common`에서 재사용한다. Phase 2가 앱 간 데이터 흐름(session + manifest)을 만들었고, phase 3이 그것을 읽게 했고, phase 4가 그 결과에 손을 댈 수 있게 했고, phase 5가 Launcher에서 그 앱으로 넘겼다. Phase 6은 그 흐름 전체를 한 테스트로 묶고, 쌓이기만 하던 manifest에 보관 한도를 뒀다. 다음 단계는 [[Roadmap]] 참고.
