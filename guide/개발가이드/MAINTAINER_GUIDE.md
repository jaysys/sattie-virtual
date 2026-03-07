# SATTIE 유지보수 개발자 가이드

## 1. 문서 목적
- 현재 코드 구조를 빠르게 이해하고 안전하게 변경하기 위한 내부 운영/개발 기준 문서입니다.
- API 동작, 저장소 구조, UI 연계, 장애 대응 포인트를 코드 기준으로 설명합니다.

## 2. 기술 스택/실행
- 백엔드: FastAPI + Uvicorn
- 이미지 처리: 내부 TIFF writer + Pillow(일부 OSM PNG decode)
- 실행 예시:
```bash
./venv/bin/uvicorn app.sattie_api:app --reload --host 0.0.0.0 --port 6001
```
- 진입 URL:
  - UI: `http://127.0.0.1:6001/ui`
  - Swagger: `http://127.0.0.1:6001/docs`

## 3. 디렉터리 구조
- `app/sattie_api.py`: FastAPI 라우트/스키마 설명/OpenAPI 텍스트
- `app/core.py`: 이미지 생성/포맷 처리/카탈로그 로더/공통 유틸
- `app/ui/index.html`: UI 마크업
- `app/ui/app.js`: UI 동작(생성/조회/다운로드/필터)
- `app/ui/styles.css`: UI 스타일
- `mock_store/random`: 랜덤 샘플 저장소
- `mock_store/osm`: OSM 생성 샘플 저장소

## 4. 생성기 설계(핵심)

### 4.1 랜덤 생성기
- 엔드포인트: `POST /images/generate`
- 역할: 단건 파일 즉시 응답(attachment)
- 저장 위치: `mock_store/random/generated/{sensor}/{level}`
- 카탈로그 반영: 안 함 (`CATALOG` 불변)

### 4.2 OSM 생성기
- 단건 파일 응답: `POST /osm/images/generate`
  - `/images/generate`와 같은 외부 연계 패턴
  - 필수: `lat/lon/zoom/sensor/level/fmt`
- 일괄 생성(JSON): `POST /osm/images/generate-all`
  - UI 호환을 위해 유지
  - 기본은 L0~L4 생성 후 JSON 응답
  - 현재 구현상 `level+fmt`를 함께 주면 단일 조합 경로도 사용 가능
- 메모리 카탈로그:
  - `OSM_SIM_CATALOG[request_id] = items`
  - `OSM_SIM_SOURCE[request_id] = source meta`

## 5. 레벨/포맷 규칙
- EO: `L0=ceos`, `L1=geotiff`, `L2=geotiff`, `L3=tiled-geotiff`, `L4=index-map`
- SAR: `L0=ceos`, `L1=geotiff`, `L2=geotiff`, `L3=tiled-geotiff`, `L4=classified-raster`
- 확장자:
  - `ceos`: `.bin`
  - 기타: `.tif`
- SAR 이미지 표현:
  - OSM 경로에서 SAR L1~L4는 흑백(강도/분류 톤)으로 생성

## 6. UI-API 연계 포인트
- OSM 생성 버튼은 현재 `POST /osm/images/generate-all` 호출
- 생성 성공 후 목록 갱신:
  - `callOsmImages()` 재조회로 즉시 목록 반영
- 필터 변경 즉시 조회:
  - `sensor/level/fmt` `change` 이벤트에서 API 재호출

## 7. 저장소/데이터 모델

### 7.1 랜덤 저장소
- 루트: `mock_store/random`
- 카탈로그: `mock_store/random/catalog.json`
- 고정 샘플 + generated 하위 동적 샘플

### 7.2 OSM 저장소
- 루트: `mock_store/osm/{request_id}`
- 산출물: `L0~L4` 파일 + `L3/tiles/*` 파생 파일
- 운영 API:
  - 상태: `GET /admin/osm-store/info`
  - 삭제: `POST /admin/osm-store/delete`

## 8. 운영 명령/검증 절차

### 8.1 기본 검증
```bash
python3 -m py_compile app/core.py app/sattie_api.py
```

### 8.2 서버 상태 확인
```bash
curl -s http://127.0.0.1:6001/health
```

### 8.3 문서 반영 확인
```bash
curl -s http://127.0.0.1:6001/openapi.json | jq '.paths["/osm/images/generate"].post.parameters'
```

## 9. 트러블슈팅

### 9.1 FastAPI `Invalid args for response field`
- 증상: `Response | dict` 같은 반환 타입 유니온에서 OpenAPI 모델 생성 실패
- 대응:
  - 라우트 반환 타입을 단일 타입(`dict` 또는 `FileResponse`)으로 정리
  - 또는 `response_model=None` 명시

### 9.2 OSM 생성 실패(502)
- 원인: 외부 타일 서버 지연/실패
- 대응:
  - 클라이언트 재시도(backoff)
  - 네트워크 상태 점검

### 9.3 TIFF 미리보기 깨짐
- UI는 `/content` 엔드포인트 사용해야 안정적
- TIFF는 서버에서 BMP 변환 후 반환

### 9.4 Swagger 문구가 즉시 안 바뀜
- `/docs`, `/openapi.json` 캐시 영향 가능
- 강력 새로고침 또는 서버 재기동

## 10. 변경 가이드

### 10.1 새 포맷 추가
1. `app/core.py`의 포맷 검증/확장자 매핑 업데이트
2. 생성 로직(`_make_dummy_image` 또는 OSM 생성 분기) 추가
3. OpenAPI 설명 문구 업데이트 (`app/sattie_api.py`)
4. UI 필터 옵션/설명 업데이트 (`app/ui/index.html`, `app/ui/app.js`)

### 10.2 새 레벨 추가
1. 레벨 enum/정규식/매핑 수정
2. 생성기(랜덤/OSM) 둘 다 반영
3. 목록/다운로드/미리보기 엔드포인트 level 검증 수정
4. UI 단계 가이드, 통계 카드 수정

### 10.3 Provider(예: Google) 추가 검토
- 별도 provider 파라미터 도입 전 라이선스/약관 검토 선행
- OSM과 동일한 타일 직접 저장 패턴을 그대로 적용 가능한지 법적 검토 필요

## 11. 권장 품질 체크리스트
- API 패턴 일관성:
  - 단건 생성기는 파일 본문 즉시 응답
  - 일괄 생성기는 JSON 메타 응답
- 저장 경로 분리 유지:
  - random -> `mock_store/random`
  - osm -> `mock_store/osm`
- OpenAPI 설명과 실제 동작 일치 확인
- UI 버튼 동작과 서버 엔드포인트 매핑 확인

## 12. 현재 주의사항
- `POST /osm/images/generate-all`은 UI 호환 목적의 일괄 생성 경로입니다.
- 외부 연계 표준은 `POST /images/generate`와 `POST /osm/images/generate`(단건 파일응답)입니다.
