# NDEX Frame v0.1 설계

**상태:** Approved design — implementation plan 작성 전 사용자 검토 필요  
**작성일:** 2026-08-30  
**제품명:** NDEX Frame  

## 1. 목적과 제품 경계

NDEX Frame은 보정과 렌더링이 끝난 Master 사진을 Instagram 등 배포 목적에 맞는 캔버스에 배치하고, 원본을 변경하지 않은 채 파생 파일을 생성하는 독립 데스크톱 애플리케이션이다.

첫 번째 사용 사례는 세로·가로 사진을 자르지 않고 3:4 캔버스에 배치하여 Instagram 업로드용 1080×1440 출력물을 만드는 것이다. Lightroom, Evoto 등 RAW 현상·보정 프로그램의 기능과 Instagram 직접 업로드 기능은 담당하지 않는다.

핵심 원칙은 다음과 같다.

1. Master 파일을 수정하거나 덮어쓰지 않는다.
2. 기본 배치 방식은 crop 없는 FIT이다.
3. Preview와 Export는 동일한 배치 계산을 사용한다.
4. Frame Preset과 Output Profile을 독립적으로 관리한다.
5. 폴더 전체 기본값과 사진별 Override를 함께 지원한다.
6. 로컬 Export 과정의 불필요한 재압축과 색 변환을 제거한다.

Instagram은 업로드한 이미지를 자체적으로 재처리하므로 완전한 무손실 전송은 보장하지 않는다. NDEX Frame의 품질 목표는 Master에서 최종 배포본을 직접 한 번만 생성하여 애플리케이션 내부의 추가 손실을 최소화하는 것이다.

## 2. 명칭과 NDEX 통합 위치

현재 애플리케이션 이름은 **NDEX Frame**으로 한다. `Publish`는 실제 플랫폼 게시 기능이 추가될 때 사용할 수 있는 상위 제품 개념으로 남겨 둔다.

NDEX Frame은 별도 `NDEX_Frame.exe`로 배포한다. 기존 프로그램에 UI를 삽입하거나 전체 NDEX shell을 재구축하지 않는다. 안정화 후 NDEX Launcher에 실행 항목을 추가할 수 있다.

새로운 `dsb-core`를 만들지 않고, 현재 저장소의 `ndex_common`에서 경로, JSON, 설정, branding 등 안정된 공통 기능만 재사용한다.

## 3. 사용자 작업 흐름

```text
Open Files / Open Folder
        ↓
파일 분석 및 thumbnail 생성
        ↓
기본 Frame Preset + 기본 Output Profile 적용
        ↓
전체 사진 Preview 검토
        ↓
필요한 사진에 Scale / X / Y Override 적용
        ↓
Export 충돌 및 오류 사전 분석
        ↓
Export Selected 또는 Export All
        ↓
완료 요약 및 출력 폴더 열기
```

폴더를 선택해도 즉시 파일을 생성하지 않는다. 모든 사진을 스캔하고 Preview와 상태를 표시한 뒤 사용자가 Export를 명시적으로 실행한다.

## 4. 단일 화면 UI

승인된 UI는 Preview 중심의 단일 화면이다.

```text
┌──────────────────────────────────────────────────────────────────┐
│ NDEX Frame   Frame Preset ▼   Output Profile ▼   Preset 관리    │
├──────────────┬──────────────────────────────┬────────────────────┤
│ Open Files   │                              │ Frame              │
│ Open Folder  │           Preview            │ Ratio        3:4   │
│              │                              │ Photo Size   100%  │
│ Thumbnails   │                              │ X / Y        0 / 0 │
│ Default      │                              │ Background   White │
│ Modified     │                              │ Reset Override     │
│ Exported     │                              │ Apply to All       │
│ Error        │                              │ Save as Preset     │
├──────────────┴──────────────────────────────┴────────────────────┤
│ Output Folder   1080×1440 · JPEG · sRGB   Export Selected / All │
└──────────────────────────────────────────────────────────────────┘
```

### 4.1 조작 규칙

- Frame Preset과 Output Profile은 상단에서 각각 선택한다.
- 앱을 열면 각각 독립적으로 지정된 기본 프리셋이 자동 적용된다.
- Ratio와 Background는 현재 작업 전체에 적용된다.
- 선택한 사진에서 Photo Size slider를 움직이거나 Preview를 drag하면 그 사진의 Image Override가 생성된다.
- 중앙 정렬이 기본값이며 X/Y 수치 입력도 지원한다.
- `Reset Override`는 선택 사진을 현재 Frame Preset의 기본 상태로 되돌린다.
- `Apply Current Framing to All`은 현재 크기와 위치를 작업 전체 기본값으로 적용한다.
- Preview 조작만으로 저장된 Frame Preset을 자동 변경하지 않는다.
- `Save as Frame Preset`을 실행해야 현재 공통 프레이밍을 새 사용자 프리셋으로 저장한다.

썸네일은 `Default`, `Modified`, `Exported`, `Error` 상태를 표시한다. Output Profile의 상세 설정은 별도 편집 창에서 관리하고, 품질·색공간·chroma·metadata는 `Advanced` 영역에 배치한다.

## 5. Frame 계산 규칙

### 5.1 FIT 100%

100%는 사진을 자르지 않고 지정된 캔버스 안에 들어가는 최대 크기를 뜻한다.

```text
fit_scale = min(canvas_width / oriented_width,
                canvas_height / oriented_height)

effective_scale = fit_scale × user_scale
```

`user_scale`의 v0.1 범위는 10%에서 100%다. 확대에 따른 crop은 허용하지 않는다.

- 3:4 세로 사진은 3:4 캔버스를 완전히 채운다.
- 5:7 세로 사진은 높이를 맞추고 좌우에 여백을 추가한다.
- 가로 사진은 너비를 맞추고 위아래에 여백을 추가한다.
- 100% 미만으로 축소하면 사진 주위의 여백이 증가한다.

### 5.2 위치

기본 위치는 정중앙이다. X/Y 이동값은 출력 해상도와 독립적으로 재사용할 수 있도록 캔버스 크기에 대한 정규화된 좌표로 저장하고, RenderPlan 생성 시 출력 pixel 좌표로 변환한다.

사진을 이동해도 사진 영역이 캔버스 밖으로 나가 crop되지 않도록 X/Y 범위를 제한한다. 사진이 캔버스의 한 축을 완전히 채우면 해당 축으로는 이동할 수 없다.

### 5.3 해상도 계산

기본 Instagram Output Profile은 고정 너비 1080px을 저장한다. 실제 높이는 Frame ratio에서 계산한다.

```text
3:4 → 1080 × 1440
4:5 → 1080 × 1350
1:1 → 1080 × 1080
```

Output Profile은 향후 `fixed_width`, `fixed_height`, `long_edge`, `fixed_dimensions` sizing mode를 지원할 수 있지만 v0.1의 기본 Instagram Profile은 `fixed_width`를 사용한다.

## 6. 렌더링과 색 관리

```text
Master Image
  → EXIF orientation 적용
  → embedded ICC를 사용해 sRGB로 변환
  → RenderPlan 계산
  → Preview: 저해상도 proxy 렌더링
  → Export: Master에서 직접 resize 및 composite
  → Output Profile에 따라 encode
  → 임시 파일 검증 후 최종 파일로 이동
```

### 6.1 Preview와 Export 일치

UI와 image processor가 각각 별도 배치 계산을 구현하지 않는다. 순수 계산 모듈이 `RenderPlan`을 만들고 Preview와 Export가 같은 결과를 사용한다. Preview는 저해상도 proxy에 RenderPlan을 비례 적용하며, Export는 Master에서 출력 pixel 좌표를 다시 계산한다.

최종 좌표와 크기의 반올림 규칙은 RenderPlan에 한 번만 정의한다. Preview와 Export의 프레이밍 오차 허용치는 1px 이하다.

### 6.2 품질 정책

- EXIF orientation을 적용하되 Master 파일은 변경하지 않는다.
- embedded ICC가 있으면 LittleCMS 기반 변환으로 sRGB에 매핑한다.
- ICC가 없는 입력은 sRGB로 간주하고 UI에 `색상 프로필 없음` 상태를 표시한다.
- Master에서 최종 크기로 Lanczos resize를 한 번만 수행한다.
- 중간 JPEG를 생성하거나 다시 읽어 Export하지 않는다.
- 투명도가 있는 입력을 JPEG로 출력할 때는 Frame background 위에 합성한다.
- 출력 파일에는 sRGB ICC profile을 포함한다.

기본 `Instagram Feed HQ` Output Profile은 다음과 같다.

```text
Sizing: fixed_width
Width: 1080 px
Format: JPEG
Quality: 95
Chroma subsampling: 4:4:4
Color space: sRGB
Embed ICC: Yes
Metadata: 촬영정보 및 저작권 유지, GPS 제거
```

## 7. Preset과 작업 데이터

### 7.1 Frame Preset

Frame Preset은 외관만 저장한다.

```json
{
  "id": "builtin.white-3x4",
  "name": "White 3:4",
  "version": 1,
  "ratio": { "width": 3, "height": 4 },
  "background": "#FFFFFF",
  "fit_mode": "fit",
  "photo_scale": 1.0,
  "x": 0.0,
  "y": 0.0
}
```

### 7.2 Output Profile

Output Profile은 파일 생성 사양만 저장한다.

```json
{
  "id": "builtin.instagram-feed-hq",
  "name": "Instagram Feed HQ",
  "version": 1,
  "sizing": { "mode": "fixed_width", "width": 1080 },
  "format": "jpeg",
  "quality": 95,
  "chroma_subsampling": "4:4:4",
  "color_space": "sRGB",
  "embed_icc": true,
  "metadata": {
    "preserve_capture": true,
    "preserve_copyright": true,
    "remove_gps": true
  }
}
```

### 7.3 기본값과 사용자 프리셋

- Frame Preset과 Output Profile은 각각 기본값 ID를 저장한다.
- 내장 프리셋은 수정·삭제할 수 없다.
- 내장 프리셋 수정 요청은 `Duplicate as Custom Preset`으로 사용자 프리셋을 만든다.
- 삭제된 사용자 기본값을 발견하면 해당 종류의 내장 기본값으로 복구한다.
- Export 시작 시 선택된 두 프리셋과 모든 Override를 immutable job snapshot으로 복사한다.

사용자 설정과 프리셋은 `ndex_common`의 경로·JSON 저장 방식을 따라 `%LOCALAPPDATA%\NDEX\Frame\` 아래에 저장한다. v0.1은 별도 프로젝트 파일 저장을 지원하지 않으며 현재 작업 세션은 메모리에 유지한다.

## 8. Import, Preview Cache, Batch

v0.1 Master 입력 형식은 JPG/JPEG, PNG, TIFF다. 폴더 Import는 지원 형식만 스캔하고 썸네일을 비동기로 생성한다.

Preview cache는 `%LOCALAPPDATA%\NDEX\Frame\cache\`에 저장하고 source path, file size, modified time을 포함한 key로 무효화한다. Cache는 재생성 가능한 파생 데이터이며 삭제되어도 Master나 Preset에 영향을 주지 않는다.

Thumbnail과 proxy 생성은 제한된 worker에서 수행한다. Full-resolution Export는 메모리 사용량과 결과 순서를 예측할 수 있도록 우선 순차 처리하고, UI thread를 차단하지 않는 background job으로 실행한다.

## 9. Export와 안전성

Export 전에 다음 항목을 분석한다.

1. Source 읽기 가능 여부와 지원 형식
2. ICC 및 orientation 처리 가능 여부
3. Frame ratio와 Output sizing의 유효성
4. Output Folder 쓰기 가능 여부
5. 기존 파일 및 batch 내부 파일명 충돌

출력 파일명은 기본적으로 원본 stem을 유지하고 선택한 Output Folder에 생성한다. 기존 파일을 자동 덮어쓰지 않는다. 사용자는 충돌 파일에 대해 `Skip` 또는 `_01`, `_02` 자동 이름 변경을 선택한다.

각 결과물은 Output Folder 안의 고유한 임시 파일로 완전히 생성하고 형식·크기를 검증한 뒤 최종 이름으로 이동한다. 한 파일의 오류는 해당 항목에 기록하고 나머지 batch를 계속 처리한다.

취소 시 이미 완료된 정상 파일은 유지하고 처리 중인 임시 파일만 제거한다. 완료 화면은 성공, 건너뜀, 실패, 취소 수와 실제 출력 경로를 표시한다.

## 10. 코드 구조

```text
ndex_frame/
├── __init__.py
├── main.py
├── core/
│   ├── models.py          # Preset, OutputProfile, Override, RenderPlan
│   ├── geometry.py        # FIT, scale, normalized position, rounding
│   └── validation.py      # Profile 및 export 사전 검증
├── imaging/
│   ├── color.py           # ICC → sRGB, metadata 정책
│   ├── renderer.py        # Master 기반 최종 렌더링
│   ├── preview.py         # Proxy 렌더링
│   └── encoders.py        # JPEG, PNG, WebP
├── services/
│   ├── importer.py        # 파일·폴더 분석
│   ├── cache.py           # Thumbnail 및 preview cache
│   ├── presets.py         # 내장/사용자 프리셋과 기본값
│   └── export_job.py      # Snapshot, progress, cancel, atomic output
├── ui/
│   ├── app.py
│   ├── main_window.py
│   ├── preview_widget.py
│   ├── thumbnail_model.py
│   └── profile_dialog.py
└── tests/

ndex_common/               # paths, settings, json, branding 재사용
```

UI는 PySide6 + Qt, image pipeline은 Pillow + LittleCMS를 사용한다. PySide6는 신규 runtime 의존성이며 Pillow는 기존 의존성을 유지한다. Core와 imaging 모듈은 Qt에 의존하지 않아 GUI 없이 단위 테스트할 수 있어야 한다.

## 11. 오류 표시

사용자가 조치할 수 있는 오류는 썸네일 상태와 상세 패널에 함께 표시한다.

- 읽을 수 없는 파일
- 지원하지 않는 pixel mode 또는 손상된 image
- ICC 변환 실패
- Output Folder 권한 문제
- 파일명 충돌
- Encode 또는 최종 이동 실패

색상 프로필 부재와 metadata 일부 손실 가능성은 경고로 표시하되 Export를 막지 않는다. Source 읽기 실패, 유효하지 않은 출력 크기, 쓸 수 없는 Output Folder는 해당 파일 또는 작업의 Export를 차단한다.

## 12. v0.1 범위

### 포함

- JPG/JPEG, PNG, TIFF Master 입력
- JPEG, PNG, WebP Output Profile
- 3:4 내장 Frame 및 Custom ratio
- FIT, 10–100% Scale, 제한된 X/Y 이동
- White, Black, Custom background
- 파일·폴더 Import, thumbnail, proxy Preview
- Frame Preset과 Output Profile 저장 및 독립 기본값
- 사진별 Override와 Apply to All
- Export Selected, Export All, progress, cancel, 오류 요약
- 안전한 collision 처리와 atomic output

### 제외

- RAW 현상·보정
- FILL 및 crop
- Instagram 직접 업로드
- Watermark, logo, blurred/dominant background
- Carousel manager
- 프로젝트 파일 저장
- Archive manifest 및 Select handoff
- 전체 NDEX UI의 Qt 통합

## 13. 테스트와 완료 기준

### 13.1 Geometry

- 3:4 세로, 5:7 세로, 가로, 정사각 사진이 crop 없이 정확한 canvas에 배치된다.
- 100%와 10% scale의 출력 크기가 정의된 반올림 규칙과 일치한다.
- X/Y 이동 한계에서 사진이 canvas 밖으로 나가지 않는다.
- 서로 다른 Preview 크기와 Output 해상도에서 구도 오차가 1px 이하다.

### 13.2 Color와 Encode

- sRGB, Adobe RGB, ICC 없는 입력을 각각 검증한다.
- Adobe RGB 입력이 sRGB로 변환되고 sRGB ICC가 포함된다.
- GPS는 제거되고 촬영정보·저작권 metadata는 보존된다.
- JPEG 기본 출력이 1080×1440, Quality 95, 4:4:4로 생성된다.
- Master에서 최종 출력까지 resize와 lossy encode가 한 번만 실행된다.

### 13.3 Preset과 상태

- 두 종류의 기본 프리셋이 독립적으로 저장·복구된다.
- 내장 프리셋은 수정·삭제되지 않는다.
- 사용자 프리셋을 복제·저장·삭제할 수 있다.
- 사진 변경 시 Override가 생성되고 Reset 시 상속 상태로 돌아간다.
- Export 중 프리셋을 변경해도 이미 시작한 job snapshot은 바뀌지 않는다.

### 13.4 Batch와 패키지

- 파일 충돌, 읽기 실패, encode 실패가 다른 파일의 처리를 막지 않는다.
- 취소 후 임시 파일이 남지 않고 완료된 결과는 정상이다.
- 원본과 기존 출력은 사용자 승인 없이 변경되지 않는다.
- 빌드된 `NDEX_Frame.exe`에서 파일·폴더 선택, Preview, Override, Export Selected/All을 smoke test한다.

## 14. 구현 순서

1. Qt 비종속 model, geometry, RenderPlan과 golden geometry test
2. ICC 변환, metadata 정책, encoder와 color/encode test
3. Preset 저장소, 기본값, immutable export snapshot
4. Import, thumbnail/proxy cache, batch export service
5. PySide6 단일 화면 UI와 Preview drag
6. 진행률, 취소, 오류·충돌 UI
7. PyInstaller build와 packaged smoke test
8. 안정화 후 NDEX Launcher 연결

이 문서가 승인된 후 별도의 implementation plan에서 파일별 변경, 테스트 우선순위, build 변경을 구체화한다.

