# Sessions and Manifests

type: architecture-note
updated: 2026-09-02
status: shipped in phase 2

## Purpose

앱 사이에서 "마지막에 뭘 하고 있었는지"와 "방금 작업이 뭘 했는지"를 두 종류의 JSON 문서로 남긴다. 사진 파일 자체는 절대 수정하지 않는다.

- **Session**: 앱 하나의 마지막 작업 맥락. Launcher의 Continue가 읽는다.
- **Manifest**: 끝난 job 하나의 결과 기록. 감사와 handoff에 쓴다.

## Locations

```text
%LOCALAPPDATA%\NDEX\sessions\{app}.json
%LOCALAPPDATA%\NDEX\manifests\{type}-{stamp}.json
%LOCALAPPDATA%\NDEX\manifests\latest-{app}-{type}.json
```

세션의 최신 스냅샷은 `settings.json`의 `shared.sessions`에도 들어간다. Launcher가 설정 한 번 읽는 것으로 4개 앱 상태를 모두 알 수 있게 하기 위해서다. 추가 전용이며 `schema_version`은 1로 유지된다.

## Session Document

```json
{
  "kind": "ndex.session",
  "schema_version": 1,
  "app": "frame",
  "updated_at": "2026-09-02T10:15:00Z",
  "folders": { "source": "D:\\Masters", "output": "D:\\Framed" },
  "last_manifest": "...\\manifests\\export-20260902T101500Z.json",
  "context": { "handoff": "...\\manifests\\select_handoff-...json" }
}
```

앱별 `folders` 키:

| App | Keys |
| --- | --- |
| ndex_one | `source`, `destination` |
| image_manager | `source` |
| auto_selector | `selected_jpg`, `raw_source`, `work` |
| frame | `source`, `output` |

세션 파일이 없으면 legacy 설정 키(`last_source`, `last_destination`, `last_selected_jpg` 등)에서 만들어 쓴다. 기존 사용자가 Continue를 잃지 않게 하기 위한 경로다.

## Manifest Document

`type`은 `backup`, `extract`, `export`, `select_handoff` 중 하나다.

```json
{
  "kind": "ndex.manifest",
  "schema_version": 1,
  "type": "select_handoff",
  "app": "image_manager",
  "created_at": "2026-09-02T10:15:00Z",
  "source": "D:\\Shoot",
  "destination": "",
  "counts": { "selected": 42 },
  "items": [{ "path": "D:\\Shoot\\IMG_1024.JPG", "status": "selected" }],
  "context": {}
}
```

파일명은 초 단위 UTC 타임스탬프다. 같은 초에 같은 type의 job이 두 번 끝나면 `-2`, `-3` 접미사가 붙어 서로 덮어쓰지 않는다.

Manifest 작성은 job 기록의 본체이고, 세션 갱신은 그 위의 편의 기능이다. 세션 쓰기가 실패해도 manifest 경로는 반환된다.

### items

`items`는 job이 실제로 도달한 파일마다 한 줄이다. `path`는 언제나 **원본 경로**다. 다시 처리할 대상이고, 대상 파일이 만들어지지 않았을 때도 남아 있는 유일한 값이기 때문이다. 재실행이 이 값을 읽는다.

취소된 job은 처리하지 못한 파일을 기록하지 않는다.

### context

type마다 다르다.

| Key | 어디에 | 내용 |
| --- | --- | --- |
| `cancelled` | backup, export | 사용자가 중간에 멈췄는가 |
| `raw_source` | extract | 원본 RAW 폴더. 재실행이 다시 매칭하려면 필요하다 |
| `recursive` | extract | 하위 폴더까지 검색했는가. 재실행이 같은 범위를 뒤지기 위해 |
| `frame_preset`, `output_profile` | export | 사용한 preset id |
| `files` | select_handoff | 넘긴 파일 목록 |
| `retry_of` | 재실행한 job 전부 | 이 job이 다시 돌린 원래 manifest 경로 |

## Continue Rules

Launcher는 `ndex_common.session.launch_args`로 실행 인자를 만든다.

1. 존재하는 폴더만 인자로 넘긴다. 사라진 폴더는 생략한다.
2. Frame은 handoff를 폴더보다 먼저 쓴다. 단 handoff가 **읽히고** 나열된 파일이 **남아 있을 때만** 그렇다.
3. 쓸 수 있는 게 하나도 없으면 `--open`만 넘긴다. 즉 Open Empty와 같다.
4. Frame에서 사용자가 파일이나 폴더를 새로 열면 handoff는 지워진다. 그러지 않으면 오래된 목록이 계속 살아난다.

manifest를 다시 읽어 보여주고 실패 항목을 다시 돌리는 쪽은 [[Job Results]]에 있다.

## Entry Points

```text
ndex_common\session.py
ndex_common\manifest.py
ndex_common\workflow.py
ndex_launcher\state.py
```

## Tests

```powershell
python -m unittest tests.test_session
python -m unittest tests.test_manifest
python -m unittest tests.test_workflow
python -m unittest discover -s ndex_launcher\tests
```
