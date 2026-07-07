# Roadmap

type: roadmap
updated: 2026-05-25

## Near Term

- NDEX Auto Selector
  - XMP sidecar가 Evoto와 Lightroom에서 실제로 어떻게 표시되는지 확인.
  - XMP 별점 외에 color label 호환성 테스트.
  - 선택 JPG의 기존 별점을 읽어 CR3 XMP에 복사하는 옵션 검토.
  - `IMG_0000` 외의 카메라 파일명 패턴 확장 여부 검토.

- NDEX Image Manager
  - Pick/rating 상태를 XMP로 export하는 기능 검토.
  - Auto Selector와 연결할 selected JPG export 흐름 정리.
  - RAW preview 품질 개선.

- NDEX One
  - 백업 로그와 검증 결과를 더 읽기 쉬운 리포트로 저장.
  - 백업 완료 후 Image Manager로 넘기는 흐름 검토.

## Mid Term

- 공통 설정 파일 구조 통합.
- 프로그램별 UI 언어와 용어 통일.
- 공통 파일 타입/브랜딩/빌드 모듈 정리.
- EXE 배포 폴더 구조 표준화.

## Questions

- NDEX 시리즈를 독립 프로그램 3개로 계속 유지할지, 런처 앱 하나로 묶을지.
- XMP를 작업용 폴더에만 만들지, 원본 라이브러리에도 선택적으로 만들지.
- Image Manager의 rating/pick 상태를 Lightroom/Evoto와 어느 정도까지 동기화할지.

