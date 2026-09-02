# Roadmap

type: roadmap
updated: 2026-09-02

## Phase Track

개발은 phase 단위로 진행된다. 현재 상태는 [[01 Development Progress]]에 있다.

| Phase | Theme | State |
| --- | --- | --- |
| 0 | 백업/사이드카/RAW 매칭 정확성 | done |
| 1 | 설정 잠금, CI, 크래시 로그, 0.9.1 재태깅 | done |
| 2 | 세션 문서, job manifest, 앱 간 handoff | done |
| 3 | job 결과를 UI에서 읽기 | done |
| 4 | 미정 | 계획 필요 |

### Phase 3에서 한 것

Phase 2는 끝난 job을 전부 manifest로 기록했지만 그 파일을 다시 읽는 곳이 없었다. Phase 3은 그 읽는 쪽을 만들었다.

- `ndex_common/report.py`: manifest를 찾아 요약하고 상태별로 묶는다.
- **Job Results** 창: 최근 job 목록과 파일별 내역. 문제 파일이 먼저 나온다.
  - Tk 앱 4개는 `ndex_common/report_dialog.py`를 공유한다.
  - Frame은 Qt라 `ndex_frame/ui/report_dialog.py`를 따로 쓴다.
- Launcher 카드마다 해당 앱의 마지막 job 결과 한 줄.
- 문제 경로 클립보드 복사, source/destination/manifest 폴더 열기.

### Phase 3에서 하지 않은 것

- **실패 항목 재실행.** 지금은 문제 경로를 복사해 주고, 같은 폴더로 job을 다시 돌리면 처리된다고 안내한다. 앱 안에서 실패분만 골라 다시 실행하는 것은 backup/extract/export 세 실행기를 각각 부분 재개 가능하게 고쳐야 해서 별도 phase로 남겼다.

## Phase 4 후보

- 실패 항목 재실행 (위 참고).
- PR #9에 남은 수동 검증 5건 처리와 4단계 handoff 통합 테스트.
- 1.0 릴리스 준비: 1.0.1에서의 설치 업그레이드 경로, 서명되지 않은 EXE 문제.

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

- NDEX Frame
  - export 실패 원인을 사용자가 바로 고칠 수 있게 안내 문구 정리.

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
- manifest를 언제까지 보관할지. 지금은 지우지 않고 계속 쌓인다.
