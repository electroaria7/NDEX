# NDEX One

type: program-note
status: usable
updated: 2026-09-02

## Purpose

NDEX One은 카메라 폴더나 SD 카드의 사진 파일을 분석하고, 촬영 날짜 기준으로 백업 폴더를 구성하는 데스크톱 백업 정리 프로그램이다.

## Main Features

- RAW/JPG 파일 스캔.
- Canon, Sony, Nikon RAW 확장자 지원.
- 촬영 날짜 기반 폴더 구성.
- 분석 후 백업 실행.
- 백업 트리 미리보기.
- 중복 파일 처리: rename, skip, overwrite.
- 복제 검증: size, sha256, none.
- dry-run 모드.
- GUI와 CLI 모두 지원.

## Job Results

버튼 행의 **Job Results...**가 최근 백업이 무엇을 복사하고 건너뛰고 실패했는지 보여준다. 실패한 파일이 아직 디스크에 있으면 같은 창의 **Retry Failed**로 그 파일만 다시 백업한다. 대상 폴더는 그 job의 manifest에서 오고, 중복 정책과 검증 방식은 지금 창에 있는 값을 쓴다. [[Architecture/Job Results]] 참고.

## Backup Structure

```text
BackupRoot/YYYY/MM/MMDD/cr3
BackupRoot/YYYY/MM/MMDD/jpg
```

## Entry Points

```text
main.py
src/gui.py
src/scanner.py
src/backup_executor.py
```

## Run

```powershell
python main.py
```

## CLI Examples

```powershell
python main.py --source E:\DCIM --destination D:\PhotoBackup --analyze
python main.py --source E:\DCIM --destination D:\PhotoBackup --backup
python main.py --source E:\DCIM --destination D:\PhotoBackup --backup --verify-mode sha256
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build.ps1 -OneFile
```

## Output

```text
dist\NDEX_One_OneFile.exe
```

## Notes

- 설정과 로그는 `%LOCALAPPDATA%\NDEX\` 아래에 저장된다.
- 기존 `%LOCALAPPDATA%\DSB\` 설정을 마이그레이션할 수 있다.
- CR3 메타데이터는 ExifTool이 있으면 가장 안정적이다.

