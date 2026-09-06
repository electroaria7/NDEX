# Roadmap

type: roadmap
updated: 2026-09-03

## Phase Track

개발은 phase 단위로 진행된다. 현재 상태는 [[01 Development Progress]]에 있다.

| Phase | Theme | State |
| --- | --- | --- |
| 0 | 백업/사이드카/RAW 매칭 정확성 | done |
| 1 | 설정 잠금, CI, 크래시 로그, 0.9.1 재태깅 | done |
| 2 | 세션 문서, job manifest, 앱 간 handoff | done |
| 3 | job 결과를 UI에서 읽기 | done |
| 4 | 실패 항목 재실행 | done |
| 5 | Launcher에서 앱으로 넘기는 재실행 | done |
| 6 | 4단계 통합 테스트와 manifest 보관 정책 | done |
| 7 | 1.0 릴리스 준비 | 계획 필요 |

### Phase 3에서 한 것

Phase 2는 끝난 job을 전부 manifest로 기록했지만 그 파일을 다시 읽는 곳이 없었다. Phase 3은 그 읽는 쪽을 만들었다.

- `ndex_common/report.py`: manifest를 찾아 요약하고 상태별로 묶는다.
- **Job Results** 창: 최근 job 목록과 파일별 내역. 문제 파일이 먼저 나온다.
  - Tk 앱 4개는 `ndex_common/report_dialog.py`를 공유한다.
  - Frame은 Qt라 `ndex_frame/ui/report_dialog.py`를 따로 쓴다.
- Launcher 카드마다 해당 앱의 마지막 job 결과 한 줄.
- 문제 경로 클립보드 복사, source/destination/manifest 폴더 열기.

### Phase 3에서 하지 않은 것

- **실패 항목 재실행.** 문제 경로 복사까지만 제공했다. Phase 4에서 처리했다.

### Phase 4에서 한 것

Phase 3이 실패 목록을 보여주기만 했다면, phase 4는 그것을 다시 돌린다. 설계는 [[Architecture/Job Results]]에 있다.

- `ndex_common/retry.py`: job의 문제 경로를 "아직 있는 파일"과 "사라진 파일"로 나눈다.
- Job Results 창의 **Retry Failed**. NDEX One / Auto Selector / Frame에만 붙는다.
- 폴더는 그 job의 manifest에서, 설정은 지금 앱에서. 확인 창이 둘 다 말한다.
- 재실행 결과는 `context.retry_of`로 원래 job을 가리키는 새 manifest로 남는다.
- 부수적으로 고친 것: 백업 manifest에 파일별 기록이 없어서 실패 경로를 낼 수 없던 문제, extract manifest에 원본 RAW 폴더가 없던 문제.

### Phase 4에서 하지 않은 것

- **Launcher에서의 재실행.** Phase 5에서 처리했다.
- **재실행 전용 진행 표시.** 재실행은 일반 job과 같은 진행 바를 쓴다. 몇 번째 재실행인지는 manifest에만 남는다.

### Phase 5에서 한 것

Launcher는 실행기가 없으니 재실행을 **넘긴다**.

- Launcher의 Job Results에 **Retry in {앱}...** 버튼. 그 앱을 그 job에서 연다.
- 세 앱이 `--retry <manifest>`를 받아 Job Results를 그 job에 맞춰 연다. 최근 목록에서 밀려난 manifest도 읽어 온다.
- 재실행 자체는 여전히 그 앱의 Retry Failed 버튼이다. 다른 프로세스가 띄운 앱이 확인 없이 파일을 쓰기 시작하는 일은 없다.

### Phase 6에서 한 것

Phase 2~5가 앱 사이의 흐름을 만들었지만 그 흐름 전체를 한 번에 확인하는 곳이 없었고, 그동안 쌓인 manifest를 치우는 곳도 없었다.

- `tests/test_workflow_handoff.py`: 백업 → 셀렉 넘기기 → 추출 → export를 임시 데이터 폴더 하나에서 끝까지 돌리고, 매 단계 뒤 Launcher가 그 앱을 Continue할 수 있는지 확인한다. PR #9에 수동으로 남아 있던 4건을 여기서 덮는다. 픽셀 작업만 대역이고 나머지는 실제 코드다.
- `ndex_common/retention.py`: type별 최신 100개만 남기고 job이 끝날 때마다 정리한다. 세션의 `last_manifest`와 Frame이 읽을 handoff는 지우지 않는다. 자세한 규칙은 [[Architecture/Sessions and Manifests]]에 있다.
- export manifest의 `counts`가 `copied` 대신 `exported`를 쓴다. 같은 manifest 안의 item 상태와 어긋나 있었다.

### Phase 6에서 하지 않은 것

- **보관 개수 설정 UI.** `KEEP_PER_TYPE` 상수 하나이고 설정 파일에 노출하지 않았다. 필요해지면 그때 붙인다.
- **Frame의 Qt export 경로까지 통합 테스트.** 그쪽은 `ndex_frame/tests`가 offscreen으로 따로 본다. 통합 테스트는 handoff를 읽는 계약까지만 확인한다.

## Phase 7 후보

- 1.0 릴리스 준비: 1.0.1에서의 설치 업그레이드 경로, 서명되지 않은 EXE 문제.
- 백업/검증 결과를 내보낼 수 있는 리포트 파일. Job Results가 화면에서는 보여주지만 파일로 나가지 않는다.
- Auto Selector UI 한국어/영어 통일. 4개 앱 중 이것만 한국어다.

## Near Term

- NDEX Auto Selector
  - XMP sidecar가 Evoto와 Lightroom에서 실제로 어떻게 표시되는지 확인.
  - XMP 별점 외에 color label 호환성 테스트.
  - 선택 JPG의 기존 별점을 읽어 CR3 XMP에 복사하는 옵션 검토.
  - `IMG_0000` 외의 카메라 파일명 패턴 확장 여부 검토.

- NDEX Image Manager
  - RAW preview 품질 개선.

- NDEX One
  - 백업 로그와 검증 결과를 더 읽기 쉬운 리포트로 저장. (Job Results로 일부 해결됨. 남은 것은 내보낼 수 있는 리포트 파일.)
  - 파일별 기록이 생겼으므로 큰 백업의 manifest 크기를 언젠가 봐야 한다.

- NDEX Frame
  - export 실패 원인을 사용자가 바로 고칠 수 있게 안내 문구 정리. (재실행이 생겼으니 문구가 더 중요해졌다.)

## Mid Term

- 공통 설정 파일 구조 통합.
- 프로그램별 UI 언어와 용어 통일. (Auto Selector만 한국어 UI다.)
- 공통 파일 타입/브랜딩/빌드 모듈 정리.
- EXE 배포 폴더 구조 표준화.

## Done

- Pick/rating 상태를 XMP로 export. (Image Manager)
- Auto Selector와 연결할 selected JPG export 흐름. (**Send to Auto Selector…**)
- 백업 완료 후 Image Manager로 넘기는 흐름. (**Open in Image Manager**)
- NDEX 시리즈를 런처 하나로 묶을지에 대한 결정: 독립 프로그램을 유지하되 [[Programs/NDEX Launcher]]가 순서를 묶는다.

## Questions

- XMP를 작업용 폴더에만 만들지, 원본 라이브러리에도 선택적으로 만들지.
- Image Manager의 rating/pick 상태를 Lightroom/Evoto와 어느 정도까지 동기화할지.
- type별 100개라는 보관 개수가 실제 사용에서 맞는지. 큰 백업 manifest가 몇 개까지 커지는지 보고 정한다.
