# SATTIE 시스템 설계 문서

## 1. 문서 목적
- 외부 연동, 내부 유지보수, 기능 확장 시 기준이 되는 단일 기술 산출물을 제공한다.
- 대상 소스:
  - `app/sattie_api.py`
  - `app/core.py`
  - `app/ui/index.html`, `app/ui/app.js`, `app/ui/styles.css`

## 2. 시스템 목표와 범위
- EO/SAR 샘플 위성영상을 L0~L4 단계로 생성/조회/다운로드/미리보기 제공
- 랜덤 시드 기반 생성기와 OSM 타일 기반 생성기를 동시에 제공
- 웹 UI와 OpenAPI(Swagger) 기반 운영/검증 지원

비범위:
- 실측 위성 정밀 처리(정사보정 정확도 보장, 물리 기반 센서 모델링)
- 사용자 인증/권한/멀티테넌시

## 3. 아키텍처 개요

### 3.1 계층 구조
- API 계층: `app/sattie_api.py`
  - 라우팅, 파라미터 검증, 응답 구성, OpenAPI 설명
- 도메인/유틸 계층: `app/core.py`
  - 이미지 생성/변환, 저장소 스캔, 포맷 검증, 카탈로그 로딩
- 프론트 UI 계층: `app/ui/*`
  - 관리/탐색 화면, 필터링, 생성/삭제 동작, 상태 카드
- 파일 저장소:
  - 랜덤: `mock_store/random`
  - OSM: `mock_store/osm`

### 3.2 런타임 상태
- 메모리 카탈로그
  - `CATALOG`: 랜덤 기본 샘플 메타 목록
  - `OSM_SIM_CATALOG`: `request_id -> [ImageItem]`
  - `OSM_SIM_SOURCE`: `request_id -> source metadata`
- 부가 설명
  - `CATALOG`
    - 서버 시작 시 `_load_catalog()`로 `mock_store/random/catalog.json`을 읽어 초기화한다.
    - `/images` 목록/상세 조회의 기준 데이터다.
    - `/images/generate` 단건 생성 결과는 `CATALOG`에 자동 추가되지 않는다(생성 파일만 저장).
  - `OSM_SIM_CATALOG`
    - OSM 생성 요청 단위의 산출물 메타를 메모리에 보관한다.
    - 키는 `request_id`, 값은 해당 요청에서 생성된 `ImageItem` 배열(L0~L4 또는 단일 레벨)이다.
    - `/osm/images`, `/osm/images/items`, `/osm/images/{request_id}` 조회의 기준 데이터다.
  - `OSM_SIM_SOURCE`
    - OSM 요청별 원본 추적 메타를 보관한다.
    - 주요 필드: `provider`, `tile_url`, `tile_x`, `tile_y`, `zoom`, `lat`, `lon`, `tile_sha256`, `tile_size_bytes`.
    - 조회 응답의 `source` 블록으로 노출되어, 생성 근거(어느 타일/좌표 기반인지) 추적에 사용된다.
  - 생명주기/복원
    - 두 OSM 메모리 맵(`OSM_SIM_CATALOG`, `OSM_SIM_SOURCE`)은 런타임 상태이며, 서버 재시작 시 메모리는 초기화된다.
    - 단, `_ensure_osm_catalog_loaded()`가 `mock_store/osm`를 스캔해 요청을 복원하므로 재기동 후에도 상당수 요청 조회가 가능하다.
  - 정합성 주의사항
    - 파일이 디스크에서 수동 삭제되면 메모리 메타와 불일치가 생길 수 있다.
    - 이 경우 다운로드/미리보기 API에서 `404 Generated file missing`이 발생할 수 있다.
- 서버 시작 시:
  - `_load_catalog()`로 랜덤 카탈로그 로딩
  - `_ensure_osm_catalog_loaded()`로 디스크의 OSM 결과 복원

## 4. 데이터 모델

### 4.1 핵심 엔티티: `ImageItem` (`app/core.py`)
- `image_id`: 이미지 식별자
- `sensor`: `eo | sar`
- `level`: `L0~L4`
- `fmt`: `ceos | geotiff | tiled-geotiff | index-map | classified-raster`
- `satellite`: 위성명 또는 `OSM-simulated`
- `acquired_at_utc`: UTC 시각 텍스트
- `file_name`: 저장 파일명
- `file_size_bytes`: 파일 크기
- `path`: 파일 절대경로
- `summary`: 요약 설명

### 4.2 포맷/레벨 규칙
- EO:
  - L0=ceos, L1=geotiff, L2=geotiff, L3=tiled-geotiff, L4=index-map
- SAR:
  - L0=ceos, L1=geotiff, L2=geotiff, L3=tiled-geotiff, L4=classified-raster
- 확장자:
  - `ceos -> .bin`
  - 그 외 -> `.tif`

## 5. 저장소 설계

### 5.1 경로
- `STORE_DIR`: `mock_store`
- `RANDOM_STORE_DIR`: `mock_store/random`
- `OSM_STORE_DIR`: `mock_store/osm`
- `RANDOM_GENERATED_DIR`: `mock_store/random/generated`
- `CATALOG_PATH`: `mock_store/random/catalog.json`

### 5.2 랜덤 저장소 정책
- 기본 샘플 카탈로그를 로드해 `/images`에 노출
- `/images/generate` 결과는 `generated/` 하위에 저장되며 `CATALOG`에 자동 편입되지 않음

### 5.3 OSM 저장소 정책
- 요청 단위 폴더: `mock_store/osm/{request_id}`
- 요청 결과(L0~L4), L3 파생 타일 보관
- 재시작 후 디스크 스캔으로 요청 복원 가능

## 6. API 설계

### 6.1 서비스/공통
- `GET /health`
- `GET /` (루트 안내)
- `GET /ui` (웹 UI)
- `app.mount("/ui/static", ...)`로 JS/CSS 제공

### 6.2 랜덤 샘플 API
- `GET /images`: 카탈로그 목록 + 필터(sensor/level/fmt/q)
- `GET /images/{image_id}`: 상세 메타
- `GET /images/{image_id}/download`: 원본 다운로드
- `GET /images/{image_id}/content`: 미리보기 콘텐츠(TIFF는 BMP 변환)
- `POST /images/generate`: 단건 파일 즉시 생성/응답(attachment)

### 6.3 OSM 샘플 API
- `POST /osm/images/generate`: 단건 파일 즉시 생성/응답(attachment)
  - 필수: `lat, lon, zoom, sensor, level, fmt`
  - 응답 헤더에 `X-OSM-Request-ID` 포함
- `POST /osm/images/generate-all`: 일괄 생성(JSON 메타)
  - 기본: L0~L4 생성 후 `{request_id, source, items}` 응답
- `GET /osm/images`: 요청 단위 목록 + 최신 요청
- `GET /osm/images/items`: 아이템 평탄 목록 + 필터(sensor/level/fmt/q/request_id)
- `GET /osm/images/{request_id}`: 요청 상세
- `GET /osm/images/{request_id}/{level}/download`: 레벨 파일 다운로드
- `GET /osm/images/{request_id}/{level}/content`: 미리보기 콘텐츠(TIFF->BMP)

### 6.4 관리 API
- `GET /admin/mock-store/info`
- `POST /admin/mock-store/rebuild`
- `POST /admin/mock-store/delete`
- `GET /admin/osm-store/info`
- `POST /admin/osm-store/delete`

## 7. 핵심 처리 시퀀스

### 7.1 랜덤 단건 생성 (`/images/generate`)
1. 쿼리 파라미터 검증(`sensor/level/fmt`)
2. 조합 검증 `_validate_generate_combo()`
3. 랜덤 seed 생성
4. 포맷에 따라 `.bin` 또는 `.tif` 생성
5. `FileResponse`로 attachment 응답

### 7.2 OSM 단건 생성 (`/osm/images/generate`)
1. 좌표/줌으로 타일 좌표 계산
2. OSM 타일 다운로드
3. L0~L4 생성 파이프라인에서 요청된 단일 조합 선택
4. 파일 저장 + 메모리 카탈로그 업데이트
5. `FileResponse`로 attachment 응답 + `X-OSM-Request-ID`

### 7.3 OSM 일괄 생성 (`/osm/images/generate-all`)
1. OSM 타일 및 인접 타일(2x2) 수집
2. L0~L4 일괄 파일 생성
3. `OSM_SIM_CATALOG`, `OSM_SIM_SOURCE` 갱신
4. JSON 메타 응답(`download_url`, `content_url` 포함)

## 8. 이미지 생성/변환 설계

### 8.1 TIFF 작성
- `_write_tiff_gray_u16()`: 16-bit grayscale TIFF
- `_write_tiff_rgb_u8()`: 8-bit RGB TIFF

### 8.2 미리보기 변환
- `_tiff_to_bmp_bytes()`: TIFF를 BMP 바이트로 변환
- `/content` 경로에서 브라우저 표시 안정성 확보

### 8.3 SAR 흑백 모사
- OSM 경로에서 SAR L1~L4는 grayscale 생성 사용
- `_rgb_to_gray_u16()`, `_rgb_to_classified_gray_u16()` 적용

## 9. UI 설계 요약
- 단일 페이지 UI (`/ui`)
- 주요 섹션:
  - 랜덤 샘플 상태/목록/상세/다운로드
  - OSM 생성/목록/상세/다운로드
- OSM 생성 버튼은 `/osm/images/generate-all` 호출
- 생성 후 `callOsmImages()` 재조회로 목록 즉시 갱신
- 필터(`sensor/level/fmt/q`) 변경 즉시 API 재조회

## 10. 오류/예외 설계
- `400`: 포맷/레벨 조합 불일치, 필수 파라미터 조합 누락
- `404`: 조회 대상 없음, 파일 누락
- `415`: TIFF 미리보기 변환 실패
- `422`: FastAPI 쿼리 검증 실패(좌표/줌/정규식)
- `502`: OSM 타일 외부 조회 실패

## 11. 운영/배포 관점
- 상태 확인: `/health`
- 문서 확인: `/docs`, `/openapi.json`
- 캐시 대응:
  - 미들웨어에서 `/`, `/ui`, `/docs`, `/redoc`, `/openapi.json` no-cache 처리
- 로그:
  - Uvicorn 로그 기준 장애 추적

## 12. 확장 설계 가이드

### 12.1 새 포맷/레벨 추가
1. `core.py` 조합 검증/확장자 규칙 반영
2. 생성 파이프라인(랜덤+OSM) 반영
3. OpenAPI 설명 문구 동기화
4. UI 필터/설명/상세 표시 동기화

### 12.2 새 Provider 추가(예: Google)
- 타일/이미지 취득 정책 및 라이선스 검토 선행 필수
- provider 별 fetch 어댑터 계층 분리 후 공통 파이프라인 재사용 권장

## 13. 현재 설계상 주의 포인트
- `generate-all` 내부 구현은 선택 파라미터(`level/fmt`) 경로도 포함하고 있어, 문서/코드 정합성을 유지해야 한다.
- 외부 연계 표준은 단건 파일 API(`/images/generate`, `/osm/images/generate`) 사용을 권장한다.
- UI는 일괄 생성 API에 의존하므로, 경로 변경 시 `app/ui/app.js` 동시 수정이 필요하다.
