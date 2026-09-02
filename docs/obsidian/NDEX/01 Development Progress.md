# Development Progress

updated: 2026-09-02
type: progress-note

## Summary

NDEX는 기존 DSB 백업 도구에서 출발해 사진 백업/선별/원본 추출/내보내기 workflow를 분리한 프로그램 시리즈다. 각 앱은 독립 실행이 가능하고, [[Programs/NDEX Launcher]]가 4단계 순서를 묶는다.

2026-09-01 이후 개발은 phase 단위로 진행된다. 각 phase는 브랜치와 PR 하나에 대응한다.

## Phase Status

| Phase | Branch | PR | Theme | State |
| --- | --- | --- | --- | --- |
| 0 | `fix/phase-0-correctness` | #6 | 백업/사이드카/RAW 매칭 정확성 | merged |
| 1 | `fix/phase-1-foundation` | #7 | 설정 잠금, CI, 크래시 로그, 0.9.1 재태깅 | merged |
| 2 | `feat/phase-2-sessions` | #9 | 세션 문서, job manifest, 앱 간 handoff | merged + 후속 수정 |
| 3 | `feat/phase-3-job-results` | #10 | job 결과를 UI에서 읽기 | merged |
| 4 | `feat/phase-4-retry-failed` | - | 실패 항목 재실행 | 작업 중 |

### Phase 4 (2026-09-02)

Phase 3이 보여준 실패 목록을 실제로 다시 돌린다. 자세한 내용은 [[Architecture/Job Results]]에 있다.

- Job Results 창의 **Retry Failed**. job을 실행하는 세 앱(NDEX One, Auto Selector, Frame)에만 붙는다.
- 폴더는 그 job의 manifest에서 온다. 설정은 지금 창에 떠 있는 값을 쓴다.
- 그 사이 사라진 파일은 세어서 제외하고, 전부 사라졌으면 재실행하지 않는다.
- 재실행 결과는 새 manifest로 남고 `context.retry_of`로 원래 job을 가리킨다.
- NDEX One이 백업의 파일별 결과를 기록하기 시작했다. 그전까지 백업 manifest에는 로그 메시지만 있어서 실패 경로를 목록에 낼 수도, 복사할 수도 없었다.
- extract manifest에 원본 RAW 폴더가 들어간다. 재실행이 다시 매칭하려면 필요하다.
- Launcher의 Job Results는 여전히 아무것도 실행하지 않는다. 대신 어느 앱을 열어야 하는지 알려준다.

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

## Verified Test Coverage

```powershell
python -m unittest discover -s tests                      # 123
python -m unittest discover -s dsb_image_manager\tests    # 11
python -m unittest discover -s ndex_auto_selector\tests   # 18
python -m unittest discover -s ndex_launcher\tests        # 12
python -m unittest discover -s ndex_frame\tests           # 147
```

2026-09-02 기준 311개 전부 통과.

## Current Direction

각 프로그램은 단독 실행 가능한 상태로 유지하되, 공통 브랜딩/빌드/설정/세션 규칙은 `ndex_common`에서 재사용한다. Phase 2가 앱 간 데이터 흐름(session + manifest)을 만들었고, phase 3이 그것을 읽게 했고, phase 4가 그 결과에 손을 댈 수 있게 했다. 다음 단계는 [[Roadmap]] 참고.
