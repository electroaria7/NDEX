# Roadmap

type: roadmap
updated: 2026-09-06

## 현재 실행 계획 — 0.9.2 이후

기존 Phase 0~6과 0.9.2 릴리스는 완료했다. 아래 계획은 기존 로드맵의 미완료 항목과
2026-09-06 코드 검토 결과를 통합한 우선순위다. 버전 번호는 목표이며, 실제 릴리스는
각 단계 검증 후 별도로 확정한다. 아래 과거 Phase 설명은 당시 구현 기록이다.

| 단계 | 목표 | 포함 범위 | 완료 기준 / 상태 |
| --- | --- | --- | --- |
| 7A / 0.9.3 목표 | 파일 처리 안전성 | Image Manager 성공 파일만 백업 완료 표시, 파일별 실패 기록, Manager 백업·내보내기와 Selector 복사의 공통 검증/원자적 반영, skip 시 RAW/XMP 보존 | 구현 및 회귀 검증 완료; 다음 배포에 포함 예정 |
| 7B | 긴 작업의 조작 가능성 | Manager 복사·XMP 작업 백그라운드 실행, Selector 취소, 종료 시 작업 정리, 중단 manifest, 재실행 진행 표시 | 작업 도중 UI 응답 유지, 취소 후 부분 파일 미노출 및 재실행 가능 |
| 7C | 실행 전 확인과 결과 공유 | 파일 수·용량·여유 공간·중복/XMP 정책 요약, CSV/HTML 결과, Frame 실패 원인별 해결 안내 | 디스크 부족·권한 오류 안내, 실패 경로 보존, 전체 목록/요약 내보내기 범위 명시 |
| 8A | 사용자 흐름 통일 | 한국어/영어 공통 문구, CR3 대신 RAW 용어, 공통 파일 타입·빌드 코드 정리 | 지원 RAW와 UI 표기가 일치하고 모든 앱에서 같은 언어·용어 사용 |
| 8B | 사진 선별 개선 | RAW 후보 충돌 선택 UI, RAW 미리보기 품질·캐시 성능, 대규모 작업 기록 성능 | 복수 후보를 비교하여 명시적으로 선택, 실사진 품질·대량 폴더 시간/메모리 측정 |
| 8C | 재현 가능한 배포 | 태그 기반 5개 앱 빌드·EXE smoke·ZIP/설치본·체크섬·릴리스 초안 자동화, 버전 입력 중복 제거 | 태그/런타임/설치본 버전 일치, 실패 시 업로드 중단, 서버 해시 일치 |
| 9 / 1.0 준비 | 실사용 호환성과 배포 신뢰성 | 실제 카메라 RAW, Lightroom/Evoto XMP 별점·color label, 기존 설치본 업데이트, 코드 서명 검토 | 아래 실사용 검증 표를 채우고 중대한 미해결 오류 없이 릴리스 판정 |

### 7A 검증 범위와 후속 조건

- 기존 대상 보존: 디스크 오류·동일 크기 손상·잘린 복사에 실패하면 이전 파일 유지.
- 이름 충돌: 복사 중 다른 작업이 같은 이름을 생성해도 rename/skip 작업이 덮어쓰지 않음.
- 성공 판정: SHA-256 및 크기 확인 후 완료로 기록. 검증의 추가 읽기 비용은 대량 작업에서 측정할 것.
- 동일 source/destination 거부. 임시 파일은 작업별 고유 이름을 사용하고 정리.
- skip은 RAW와 XMP 모두 보존. 기존 RAW의 XMP만 갱신하는 기능은 별도 명시적 작업으로 검토.
- 사진 파일과 XMP를 하나의 트랜잭션으로 보장하는 범위는 아직 포함하지 않음.
- NDEX One의 기존 복사/검증 구현은 유지. 공통화는 기존 취소·검증 정책을 보존하는 후속 작업으로 진행.

### 실제 자료가 필요한 완료 조건

| 항목 | 필요한 자료/환경 | 현재 상태 |
| --- | --- | --- |
| RAW 미리보기 | 사용 권한이 있는 Canon/Nikon/Sony 실제 RAW, 내장 미리보기 유무별 샘플 | 합성 파일 매칭 검증만 완료 |
| XMP 호환성 | Lightroom/Evoto 설치 환경과 기대 별점·색상 라벨 | NDEX 생성/병합 테스트 완료, 외부 앱 해석 미검증 |
| 설치 업데이트 | 격리된 Windows 환경, 0.9.1 및 과거 1.0.1 설치본, 설정 보존 시나리오 | 0.9.2 신규 설치/제거 완료, 업데이트 미검증 |
| 서명 | 배포 주체와 인증서/서명 서비스 결정 | 미착수; 취득·비용 결정을 구현 완료로 간주하지 않음 |

### 기존 후보에서 이미 완료된 것

- 선택 JPG 별점을 RAW XMP로 복사하는 옵션: 구현 및 테스트 완료.
- Canon IMG, Nikon DSC, Sony DSC 파일명 토큰: 구현 및 테스트 완료. 추가 패턴은 실제 실패 샘플 기준.
- 공유 설정 파일과 Apps/Docs 배포 폴더 구조: 구현 완료. 남은 것은 스키마 마이그레이션과 중복 코드 정리.
- Launcher 앱 연결, 실패 재실행, 기록 보관 정책, 동시 기록 보호, 긴 경로 스크롤: 0.9.2에 포함.

### 측정 후 결정할 항목

- 기록 보관 개수 UI와 대형 manifest 최적화: 현재 종류별 최신 100개, 성공 상태별 최대 500개 기록.
  실패는 보존한다. 전체 CSV/HTML 리포트는 이 제한과 별개로 전체 내역을 보관할지 먼저 결정한다.
- XMP를 원본 라이브러리에도 쓸지, 외부 앱과 양방향 동기화할지: 외부 편집 보존/충돌 정책 확정 후 검토.
- 설치 파일 크기와 첫 실행 시간: 0.9.2 설치본 약 626 MB를 기준으로 측정 후 공유 의존성 배포 방식을 비교.

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
| 7~9 | 안전성 → 사용성 → 배포/실사용 검증 | 위 통합 계획으로 대체 |

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
  - 선택 JPG 별점 복사와 Canon/Nikon/Sony 파일명 토큰 지원은 완료. 추가 패턴은 실제 샘플 기준으로 검토.

- NDEX Image Manager
  - RAW preview 품질 개선.

- NDEX One
  - 백업 로그와 검증 결과를 더 읽기 쉬운 리포트로 저장. (Job Results로 일부 해결됨. 남은 것은 내보낼 수 있는 리포트 파일.)
  - 파일별 기록이 생겼으므로 큰 백업의 manifest 크기를 언젠가 봐야 한다.

- NDEX Frame
  - export 실패 원인을 사용자가 바로 고칠 수 있게 안내 문구 정리. (재실행이 생겼으니 문구가 더 중요해졌다.)

## Mid Term

- 공통 설정 스키마 마이그레이션 정책 정리 (공유 파일은 이미 통합).
- 프로그램별 UI 언어와 용어 통일. (Auto Selector만 한국어 UI다.)
- 공통 파일 타입/브랜딩/빌드 모듈 정리.
- Apps/Docs 배포 폴더 구조 표준화는 완료. 남은 것은 배포 자동화.

## Done

- Pick/rating 상태를 XMP로 export. (Image Manager)
- Auto Selector와 연결할 selected JPG export 흐름. (**Send to Auto Selector…**)
- 백업 완료 후 Image Manager로 넘기는 흐름. (**Open in Image Manager**)
- NDEX 시리즈를 런처 하나로 묶을지에 대한 결정: 독립 프로그램을 유지하되 [[Programs/NDEX Launcher]]가 순서를 묶는다.

## Questions

- XMP를 작업용 폴더에만 만들지, 원본 라이브러리에도 선택적으로 만들지.
- Image Manager의 rating/pick 상태를 Lightroom/Evoto와 어느 정도까지 동기화할지.
- type별 100개라는 보관 개수가 실제 사용에서 맞는지. 큰 백업 manifest가 몇 개까지 커지는지 보고 정한다.
