# SATTIE 외부 클라이언트 개발가이드

## 1. 개요
- 서비스명: SATTIE (Virtual Satellite Imagery Service)
- 기본 주소(로컬 예시): `http://127.0.0.1:6001`
- 인증: 현재 없음
- 응답 형태:
  - 메타 조회: `application/json`
  - 파일 다운로드: `application/octet-stream` 또는 `image/tiff`
  - 브라우저 미리보기: TIFF는 BMP 변환(`image/bmp`) 후 반환

## 2. 핵심 개념
- 센서(`sensor`): `eo`, `sar`
- 레벨(`level`): `L0`~`L4`
- 포맷(`fmt`) 매핑 규칙:
  - EO: `L0=ceos`, `L1=geotiff`, `L2=geotiff`, `L3=tiled-geotiff`, `L4=index-map`
  - SAR: `L0=ceos`, `L1=geotiff`, `L2=geotiff`, `L3=tiled-geotiff`, `L4=classified-raster`
- 파일 확장자:
  - `ceos` -> `.bin`
  - 그 외 -> `.tif`

## 3. API 패턴 요약
- 랜덤 단건 생성(파일 즉시 응답): `POST /images/generate`
- OSM 단건 생성(파일 즉시 응답): `POST /osm/images/generate`
- OSM 일괄 생성(JSON 메타 응답): `POST /osm/images/generate-all`
- 목록/상세/다운로드/미리보기 조회:
  - 랜덤 카탈로그: `/images`, `/images/{image_id}`, `/images/{image_id}/download`, `/images/{image_id}/content`
  - OSM 카탈로그: `/osm/images`, `/osm/images/items`, `/osm/images/{request_id}`, `/osm/images/{request_id}/{level}/download`, `/osm/images/{request_id}/{level}/content`

## 4. 빠른 시작

### 4.1 상태 확인
```bash
curl -s http://127.0.0.1:6001/health
```

### 4.2 랜덤 단건 생성 다운로드
```bash
curl -L -X POST \
  "http://127.0.0.1:6001/images/generate?sensor=eo&level=L2&fmt=geotiff" \
  -o eo_l2.tif
```

### 4.3 OSM 단건 생성 다운로드 (`/images/generate`와 동일 패턴)
```bash
curl -L -X POST \
  "http://127.0.0.1:6001/osm/images/generate?lat=37.5665&lon=126.9780&zoom=14&sensor=eo&level=L2&fmt=geotiff" \
  -o osm_eo_l2.tif -D headers.txt
```
- 응답 헤더 `X-OSM-Request-ID`를 함께 받으면 이후 OSM 조회 API 연계에 사용할 수 있습니다.

### 4.4 OSM 일괄 생성 후 항목별 다운로드
```bash
curl -s -X POST \
  "http://127.0.0.1:6001/osm/images/generate-all?lat=35.1796&lon=129.0756&zoom=13&sensor=sar"
```
- 응답 `items[]`의 `download_url`을 순회 호출해 L0~L4를 개별 저장합니다.

## 5. 엔드포인트 상세

### 5.1 `POST /images/generate`
- 목적: 랜덤 기반 단일 샘플 파일 즉시 생성+다운로드
- 필수 쿼리: `sensor`, `level`, `fmt`
- 성공: 파일 본문(attachment)
- 실패:
  - `400`: 조합 불일치/미지원 포맷

예시:
```bash
curl -L -X POST \
  "http://127.0.0.1:6001/images/generate?sensor=sar&level=L4&fmt=classified-raster" \
  -o sar_l4.tif
```

### 5.2 `POST /osm/images/generate`
- 목적: OSM 타일 기반 단일 샘플 파일 즉시 생성+다운로드
- 필수 쿼리: `lat`, `lon`, `zoom`, `sensor`, `level`, `fmt`
- 성공: 파일 본문(attachment), `X-OSM-Request-ID` 헤더 포함
- 실패:
  - `400`: `sensor/level/fmt` 조합 불일치
  - `422`: `lat/lon/zoom` 검증 실패
  - `502`: OSM 타일 수신 실패

예시:
```bash
curl -L -X POST \
  "http://127.0.0.1:6001/osm/images/generate?lat=35.1796&lon=129.0756&zoom=13&sensor=sar&level=L4&fmt=classified-raster" \
  -o osm_sar_l4.tif -D headers.txt
```

### 5.3 `POST /osm/images/generate-all`
- 목적: OSM 기반 L0~L4 일괄 생성 후 메타데이터(JSON) 응답
- 필수 쿼리: `lat`, `lon`, `zoom`, `sensor`
- 선택 쿼리: `level`, `fmt` (둘 다 같이 제공 시 단일 조합 생성 경로 사용)
- 성공: JSON(`request_id`, `source`, `items`)

예시:
```bash
curl -s -X POST \
  "http://127.0.0.1:6001/osm/images/generate-all?lat=37.5665&lon=126.9780&zoom=14&sensor=eo"
```

### 5.4 `GET /images` (랜덤 카탈로그 목록)
- 필터: `sensor`, `level`, `fmt`, `q`
- 반환: `{count, items[]}`

### 5.5 `GET /osm/images/items` (OSM 전체 아이템 평탄 목록)
- 필터: `sensor`, `level`, `fmt`, `q`, `request_id`
- 반환: `{count, items[]}`

## 6. 응답 필드 가이드
- 공통 아이템 주요 필드:
  - `image_id`
  - `sensor`
  - `level`
  - `fmt`
  - `satellite`
  - `acquired_at_utc`
  - `file_name`
  - `file_size_bytes`
  - `summary`
- OSM 아이템 추가 필드:
  - `request_id`
  - `download_url`
  - `content_url`

## 7. 권장 연동 패턴

### 패턴 A: 파일 즉시 수신(권장)
- 단건 생성 API를 직접 호출하고 파일을 저장
- 대상:
  - 랜덤: `/images/generate`
  - OSM: `/osm/images/generate`

### 패턴 B: OSM 일괄 생성 후 링크 기반 수신
1. `/osm/images/generate-all` 호출
2. `items[]`에서 `download_url` 추출
3. 각 URL 다운로드

## 8. 오류 처리 가이드
- `400`: 파라미터 조합 오류
  - 조합 매핑 표를 기준으로 요청값 재검증
- `404`: 조회/다운로드 대상 없음
  - `request_id`, `image_id`, `level` 오타 여부 확인
- `422`: 입력값 범위 오류
  - `lat`, `lon`, `zoom`, `level` 형식 점검
- `502`: 외부 OSM 타일 실패
  - 지수 백오프 재시도(예: 1s/2s/4s)

## 9. 클라이언트 구현 체크리스트
- 파일 다운로드 시 `-L`(redirect), timeout, retry 설정
- 파일명은 `Content-Disposition` 기준으로 저장
- OSM 단건 생성 시 `X-OSM-Request-ID` 로깅
- TIFF 웹 표시가 필요하면 `/content` 엔드포인트 사용

## 10. 참고 API
- 서비스: `GET /health`
- 루트/문서: `GET /`, `GET /docs`, `GET /openapi.json`

