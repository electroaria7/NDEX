# 배포본 검증 — 2026-09-05

## 빌드와 자동 검증

- 기준 런타임: main `9e4d8c4`, NDEX 0.9.1 (unreleased 변경 포함).
- Windows / Python 3.12.10 / PyInstaller 6.11.1.
- 별도 `.venv`에서 `requirements.lock` 설치: Pillow 12.3.0, PySide6 6.11.2.
  기존 시스템 Pillow 12.2.0은 변경하지 않았다.
- 5개 EXE 전체 재빌드, Apps/Docs 배포 폴더 조립, SHA256SUMS 검증 성공.
- 단위·통합 테스트 366개 통과 (168 + 11 + 19 + 13 + 155).
- 빌드 스크립트가 pip/PyInstaller/하위 PowerShell 실패를 즉시 전파하도록
  수정했다. 실패 도구를 주입하는 테스트로 오래된 EXE 조립 방지를 검증했다.

`tests/smoke_release.py`는 배포 폴더와 존재하지 않는 증거 폴더를 받는다.
임시 사진을 만들고 LOCALAPPDATA를 격리하여 아래를 실제 EXE로 실행한다.

1. NDEX One: JPG/CR3 백업 2개, SHA-256 동일성, 작업 기록 확인.
2. Image Manager: 실제 카탈로그의 이미지 2개 확인.
3. Auto Selector: 원본 매칭, CR3 복제 해시, XMP 생성, 작업 기록 확인.
4. Frame: 1080×1440 JPEG, sRGB ICC, 저작권 유지, GPS 제거, 원본 해시 유지.

위 검증은 포터블 폴더와 실제 설치된 폴더 양쪽에서 통과했다.
RAW는 파일 매칭용 합성 데이터이므로 실제 카메라 RAW 디코딩은 검증하지 않았다.

```powershell
python tests/smoke_release.py release/NDEX_v0.9.1 .build_tools/new-smoke-evidence
```

## 실제 GUI 검증

- Launcher Continue → NDEX One: 원본/백업 폴더 사전 입력, 자동 백업 미실행.
- NDEX One → Image Manager: 백업 폴더 전달, 사진 2개 스캔, JPG 미리보기.
- Image Manager → Frame: JPG를 Pick으로 지정하고 handoff로 한 장 가져오기.
- Image Manager → Auto Selector: 앱 실행 및 셀렉 JPG 폴더 전달 안내 확인.
- Frame GUI Export All: 기존 출력 충돌 감지, Auto rename으로 기존 파일 보존,
  1 exported / 0 failed, export manifest 및 실제 이미지 속성 확인.

## 설치 패키지

Inno Setup 6.7.3을 [공식 배포 페이지](https://jrsoftware.org/isdl.php)에서
확인하여 준비했다. 컴파일러 설치 파일의 Authenticode 상태는 Valid였다.
NDEX 설치 파일은 프로젝트의 기존 서명 없는 빌드 설정을 사용한다.

- `release/NDEX_Setup_0.9.1.exe`: 626,374,598 bytes.
- SHA-256: `d8a8a309b0d6fc1ed4ecf99383bd8e16daec5d929e9170aeb3264c757e449d20`.
- 사용자 UAC 승인 후 `.build_tools/installed-validation`에 관리자 설치 성공.
- 설치 종료 코드 0, 재부팅 불필요, 레지스트리 버전 0.9.1 확인.
- 설치된 파일의 체크섬과 실제 EXE 스모크 테스트 통과.
- 사용자 UAC 승인 후 제거 종료 코드 0, 재부팅 불필요.
  테스트 설치 폴더 및 HKLM 제거 등록 키 삭제까지 확인.

## 남은 검증 및 발견 사항

- Launcher 초기 크기의 2×2 카드 배치에서 긴 작업 경로가 있으면 버튼/하단
  영역이 잘렸다. 최대화하면 정상 표시되었다. 콘텐츠 높이에 따른 초기 크기
  조정 또는 스크롤 대응이 필요하다.
- 이전 1.0.1 설치본에서의 업그레이드/다운그레이드 경로는 이번 신규 설치와
  별개이며 미검증이다. README의 기존 버전 제거 안내를 유지한다.
- Lightroom/Evoto의 실제 XMP 해석, 카메라 RAW 디코딩은 미검증이다.
- 빌드·실행 증거는 `.build_tools/release-build.log`, `installer-build.log`,
  `install-validation.log`, `uninstall-validation.log`, `release-validation-2/result.json`,
  `installed-smoke/result.json`에 보존했다.
- 기존 공개 ZIP은 덮어쓰지 않았고 GitHub Release를 게시하지 않았다.
