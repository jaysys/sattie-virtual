    const $ = (id) => document.getElementById(id);
    const LEVEL_ORDER = ["L0", "L1", "L2", "L3", "L4"];
    let jobTimer = null;
    let jobStartedAt = 0;
    let jobRunning = false;
    let deleteConfirmResolver = null;
    let osmItems = [];
    let osmSelected = null;
    let osmRequestId = "";
    const LEVEL_GUIDE = {
      L0: {
        formats: "Raw binary, CEOS",
        formatTooltip: "Raw binary: 센서 원시신호 / CEOS: 위성원시자료 교환 포맷",
        imageState: "원시 텔레메트리/신호, 사람 판독 어려움",
        extras: ["패킷/라인 헤더", "센서 수집 시각", "기초 획득 메타"],
        usage: "복원/재처리 입력",
        remarks: "다른 이미지 포맷 적용 전 단계"
      },
      L1: {
        formats: "GeoTIFF, CEOS L1A",
        formatTooltip: "GeoTIFF: 공간좌표 포함 래스터 / CEOS L1A: 기초 보정 단계 위성자료",
        imageState: "기초 보정된 영상(기하/방사 보정)",
        extras: ["밴드/비트심도", "기본 보정 파라미터", "센서/촬영 메타"],
        usage: "전문 분석 시작점",
        remarks: "기타 포맷: JPEG2000, NITF"
      },
      L2: {
        formats: "GeoTIFF (+RPC/DEM)",
        formatTooltip: "GeoTIFF + RPC/DEM: 정밀 지오리퍼런싱/정사보정에 필요한 보조정보 포함",
        imageState: "지리 좌표계 정합된 분석용 영상",
        extras: ["좌표계/해상도", "RPC 계수", "DEM 연계 정보"],
        usage: "측정/정밀 분석",
        remarks: "기타 포맷: COG, NetCDF, HDF5"
      },
      L3: {
        formats: "Mosaic GeoTIFF, Tiles",
        formatTooltip: "Mosaic: 여러 장면 결합 영상 / Tiles: 웹 지도용 타일 분할 포맷",
        imageState: "서비스용 모자이크/타일 레이어",
        extras: ["타일 인덱스", "모자이크 경계", "표시 최적화 정보"],
        usage: "지도 서비스/웹 제공",
        remarks: "기타 포맷: MBTiles, WMTS, XYZ Tiles"
      },
      L4: {
        formats: "Classified raster, index map",
        formatTooltip: "Classified raster: 분류코드 래스터 / index map: 지수값 기반 주제도",
        imageState: "지수/분류 결과(해석 산출물)",
        extras: ["분류 코드 체계", "지수 값 범위", "판정 기준 정보"],
        usage: "의사결정/리포트",
        remarks: "기타 포맷: GeoPackage, GeoJSON, CSV"
      }
    };

    function pretty(obj) { return JSON.stringify(obj, null, 2); }
    function toNum(v) { return Number.isFinite(v) ? v : 0; }
    function bytesToLabel(n) {
      const b = Number(n || 0);
      if (b < 1024) return `${b} B`;
      if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
      return `${(b / (1024 * 1024)).toFixed(2)} MB`;
    }

    function toMockStoreRelative(path) {
      const s = String(path || "");
      const k = "/mock_store/";
      const i = s.indexOf(k);
      if (i >= 0) return `mock_store/${s.slice(i + k.length)}`;
      if (s.endsWith("/mock_store")) return "mock_store";
      return s || "-";
    }

    function formatElapsed(ms) {
      const total = Math.max(0, Math.floor(ms / 1000));
      const mm = String(Math.floor(total / 60)).padStart(2, "0");
      const ss = String(total % 60).padStart(2, "0");
      return `${mm}:${ss}`;
    }

    function tickJobClock() {
      const now = new Date();
      $("jobNow").textContent = now.toLocaleTimeString("ko-KR", { hour12: false });
      $("jobElapsed").textContent = formatElapsed(Date.now() - jobStartedAt);
    }

    function openJobModal(title, msg) {
      jobRunning = true;
      jobStartedAt = Date.now();
      $("jobTitle").textContent = title;
      $("jobMsg").textContent = msg;
      $("jobCloseBtn").disabled = true;
      $("jobModal").classList.remove("done");
      $("jobModal").classList.add("show");
      tickJobClock();
      clearInterval(jobTimer);
      jobTimer = setInterval(tickJobClock, 1000);
      $("rebuildBtn").disabled = true;
    }

    function finishJobModal(ok, msg) {
      jobRunning = false;
      clearInterval(jobTimer);
      jobTimer = null;
      tickJobClock();
      $("jobTitle").textContent = ok ? "샘플 생성 완료" : "샘플 생성 실패";
      $("jobMsg").textContent = msg;
      $("jobCloseBtn").disabled = false;
      $("jobModal").classList.add("done");
      $("rebuildBtn").disabled = false;
    }

    function closeJobModal() {
      if (jobRunning) return;
      $("jobModal").classList.remove("show");
    }

    function openDeleteConfirm(title = "샘플 삭제 확인", message = "mock_store 아래 생성 샘플을 모두 삭제합니다. 계속할까요?") {
      return new Promise((resolve) => {
        deleteConfirmResolver = resolve;
        const titleEl = $("confirmTitle");
        const msgEl = $("confirmMsg");
        if (titleEl) titleEl.textContent = title;
        if (msgEl) msgEl.textContent = message;
        $("confirmModal").classList.add("show");
      });
    }

    function resolveDeleteConfirm(ok) {
      $("confirmModal").classList.remove("show");
      if (deleteConfirmResolver) {
        const done = deleteConfirmResolver;
        deleteConfirmResolver = null;
        done(Boolean(ok));
      }
    }

    function buildQuery(params) {
      const q = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && String(v).trim() !== "") q.set(k, String(v).trim());
      });
      return q.toString();
    }

    function applyOsmPreset(value) {
      if (!value) return;
      const [lat, lon] = String(value).split(",");
      if (!lat || !lon) return;
      $("osmLat").value = lat;
      $("osmLon").value = lon;
    }

    function clearOsmPresetSelections() {
      const kr = $("osmPresetKR");
      const kp = $("osmPresetKP");
      if (kr) kr.value = "";
      if (kp) kp.value = "";
    }

    function renderLevelGuide() {
      const body = $("levelGuideBody");
      body.innerHTML = "";
      LEVEL_ORDER.forEach((lv) => {
        const g = LEVEL_GUIDE[lv];
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><strong>${lv}</strong></td>
          <td><span class="fmt-tip" data-tip="${g.formatTooltip || g.formats}">${g.formats}</span></td>
          <td>${g.imageState}</td>
          <td>${g.extras.map((x) => `<small>${x}</small>`).join("<br/>")}</td>
          <td>${g.usage}</td>
          <td>${g.remarks || "-"}</td>
        `;
        body.appendChild(tr);
      });
    }

    function setStep(level) {
      document.querySelectorAll(".step").forEach((x) => {
        if (x.dataset.level === level) x.classList.add("on");
        else x.classList.remove("on");
      });
    }

    function renderTags(elId, items) {
      const el = $(elId);
      if (!items || !items.length) {
        el.innerHTML = '<span class="warn">정보 없음</span>';
        return;
      }
      el.innerHTML = items.map((x) => `<span class="pill">${x}</span>`).join("");
    }

    function renderOsmSelected(item) {
      osmSelected = item || null;
      if (!item) {
        $("osmImageKv").innerHTML = '<div class="k">상태</div><div class="warn">선택된 OSM 이미지가 없습니다.</div>';
        $("osmPreviewWrap").innerHTML = '<span class="warn">미리보기할 이미지가 없습니다.</span>';
        $("osmDownloadHint").textContent = "생성 후 레벨을 선택하면 다운로드할 수 있습니다.";
        return;
      }
      $("osmImageKv").innerHTML = `
        <div class="k">Request ID</div><div>${osmRequestId || "-"}</div>
        <div class="k">Image ID</div><div>${item.image_id}</div>
        <div class="k">Sensor / Level</div><div>${item.sensor.toUpperCase()} / ${item.level}</div>
        <div class="k">Format</div><div>${item.fmt}</div>
        <div class="k">Acquired(UTC)</div><div>${item.acquired_at_utc}</div>
        <div class="k">Summary</div><div>${item.summary}</div>
      `;
      $("osmDownloadHint").innerHTML = `선택 파일: <strong>${item.file_name}</strong> (${bytesToLabel(item.file_size_bytes)})`;

      if (item.level === "L0" || String(item.fmt).toLowerCase() === "ceos") {
        $("osmPreviewWrap").innerHTML = '<span class="warn">L0 raw(bin)는 브라우저 이미지 미리보기를 지원하지 않습니다.</span>';
        return;
      }
      const src = `${item.content_url}${item.content_url.includes("?") ? "&" : "?"}_=${Date.now()}`;
      $("osmPreviewWrap").innerHTML = `<img src="${src}" alt="${item.image_id}" />`;
    }

    function renderOsmList(items) {
      const wrap = $("osmImagesList");
      if (!items || !items.length) {
        wrap.innerHTML = '<span class="warn">생성 결과가 없습니다.</span>';
        renderOsmSelected(null);
        return;
      }
      wrap.innerHTML = "";
      items.forEach((x) => {
        const b = document.createElement("button");
        b.className = "secondary";
        b.textContent = `${x.level} | ${x.fmt} | ${x.file_name}`;
        b.onclick = () => renderOsmSelected(x);
        wrap.appendChild(b);
      });
      renderOsmSelected(items[0]);
    }

    function updateOsmStats(items) {
      const by = { L0: 0, L1: 0, L2: 0, L3: 0, L4: 0 };
      (items || []).forEach((x) => { if (x && x.level in by) by[x.level] += 1; });
      $("osmTotal").textContent = (items || []).length;
      $("osmL0").textContent = by.L0;
      $("osmL1").textContent = by.L1;
      $("osmL2").textContent = by.L2;
      $("osmL34").textContent = by.L3 + by.L4;
    }

    function renderSelectedImage(p) {
      if (!p) {
        $("imageKv").innerHTML = '<div class="k">상태</div><div class="warn">선택된 이미지가 없습니다.</div>';
        renderTags("extraInfo", []);
        renderTags("usageInfo", []);
        $("previewWrap").innerHTML = '<span class="warn">미리보기할 이미지가 없습니다.</span>';
        return;
      }
      $("pid").value = p.image_id;
      $("downloadHint").innerHTML = `선택된 파일: <strong>${p.file_name}</strong> (${bytesToLabel(p.file_size_bytes)})`;
      setStep(p.level);
      const guide = LEVEL_GUIDE[p.level] || { extras: [], usage: "" };
      $("imageKv").innerHTML = `
        <div class="k">Image ID</div><div>${p.image_id}</div>
        <div class="k">Sensor / Level</div><div>${p.sensor.toUpperCase()} / ${p.level}</div>
        <div class="k">Format</div><div>${p.fmt}</div>
        <div class="k">Satellite</div><div>${p.satellite}</div>
        <div class="k">Acquired(UTC)</div><div>${p.acquired_at_utc}</div>
        <div class="k">Summary</div><div>${p.summary}</div>
      `;
      const viewerHint = p.level === "L0"
        ? ["일반 이미지 뷰어 비권장", "신호/아카이브 전용 도구 필요"]
        : ["GIS 툴(QGIS 등) 권장", "웹 지도/타일 연계 가능"];
      renderTags("extraInfo", guide.extras);
      renderTags("usageInfo", [guide.usage, ...viewerHint]);

      const name = String(p.file_name || "").toLowerCase();
      const webExt = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".tif", ".tiff"];
      const displayable = webExt.some((ext) => name.endsWith(ext));
      if (!displayable) {
        $("previewWrap").innerHTML = `<span class="warn">이 파일은 브라우저에서 직접 미리보기가 안됩니다.</span> <span class="muted">(${p.file_name})</span>`;
      } else {
        const src = `/images/${encodeURIComponent(p.image_id)}/content`;
        $("previewWrap").innerHTML = `<img src="${src}" alt="${p.image_id}" />`;
      }
    }

    function renderImagesList(items) {
      const wrap = $("imagesList");
      if (!items.length) {
        wrap.innerHTML = '<span class="warn">검색 결과가 없습니다.</span>';
        wrap.style.maxHeight = "none";
        renderSelectedImage(null);
        return;
      }
      wrap.innerHTML = "";
      items.forEach((x) => {
        const b = document.createElement("button");
        b.className = "secondary";
        b.textContent = `${x.image_id} | ${x.sensor}/${x.level} | ${x.fmt}`;
        b.onclick = () => renderSelectedImage(x);
        wrap.appendChild(b);
      });
      const first = wrap.querySelector("button");
      if (first && items.length > 10) {
        const st = window.getComputedStyle(first);
        const mb = parseFloat(st.marginBottom || "0");
        const mt = parseFloat(st.marginTop || "0");
        const itemH = first.getBoundingClientRect().height + mb + mt;
        const panelPad = 16; // images-list vertical padding (8px * 2)
        wrap.style.maxHeight = `${Math.ceil(itemH * 10 + panelPad)}px`;
      } else {
        wrap.style.maxHeight = "none";
      }
      renderSelectedImage(items[0]);
    }

    function updateStats(items) {
      const by = { L0: 0, L1: 0, L2: 0, L3: 0, L4: 0 };
      items.forEach((x) => { by[x.level] = toNum(by[x.level]) + 1; });
      $("sTotal").textContent = items.length;
      $("sL0").textContent = by.L0;
      $("sL1").textContent = by.L1;
      $("sL2").textContent = by.L2;
      $("sL34").textContent = by.L3 + by.L4;
    }

    async function getJson(url, options = {}) {
      const res = await fetch(url, options);
      const text = await res.text();
      let body;
      try { body = JSON.parse(text); } catch { body = text; }
      return { res, body };
    }

    async function callHealth() {
      try {
        const { body } = await getJson("/health");
        $("healthBanner").textContent = `서비스 상태: ${body.status} / 샘플 ${body.images}건`;
      } catch (e) {
        $("healthBanner").innerHTML = `<span class="warn">상태 조회 실패: ${String(e)}</span>`;
      }
    }

    async function loadMockStoreInfo() {
      try {
        const { body } = await getJson("/admin/mock-store/info");
        const folders = body.image_folders || [];
        const files = body.image_files || [];
        const storeFolders = body.store_folders || [];
        const storeFiles = body.store_files || [];
        const locked = body.disabled ? " / 삭제 잠금 상태" : "";
        $("adminStatus").textContent = `카탈로그(/images): ${body.image_count}개, 카탈로그 파일 ${files.length}개 / 스토어 전체 누적: 폴더 ${storeFolders.length}개, 파일 ${storeFiles.length}개${locked}`;
        if (!files.length) {
          $("folderList").innerHTML = '<span class="warn">생성된 파일이 없습니다.</span>';
          return;
        }
        $("folderList").innerHTML = files.map((f) => `<div class="folder-item">${f}</div>`).join("");
      } catch (e) {
        $("adminStatus").innerHTML = `<span class="warn">스토어 정보 조회 실패: ${String(e)}</span>`;
      }
    }

    async function refreshStatus() {
      await Promise.all([callHealth(), loadMockStoreInfo()]);
    }

    async function rebuildSamples() {
      if (jobRunning) return;
      openJobModal("샘플 위성영상 생성 중", "현재 백그라운드 작업이 진행 중입니다. 완료되면 닫기 버튼이 활성화됩니다.");
      try {
        const { res, body } = await getJson("/admin/mock-store/rebuild", { method: "POST" });
        if (!res.ok) {
          $("detailOut").textContent = pretty({ status: res.status, body });
          const reason = body && body.detail
            ? String(body.detail)
            : "샘플 생성 요청에 실패했습니다. 상세 내용은 Raw API 응답을 확인해주세요.";
          finishJobModal(false, reason);
          return;
        }
        $("detailOut").textContent = pretty({ status: res.status, body });
        await callImages();
        await refreshStatus();
        finishJobModal(true, "샘플 생성이 완료되었습니다. 확인 후 닫기를 누르세요.");
      } catch (e) {
        $("detailOut").textContent = pretty({ error: String(e) });
        finishJobModal(false, `오류가 발생했습니다: ${String(e)}`);
      }
    }

    async function deleteSamples() {
      const ok = await openDeleteConfirm(
        "샘플 삭제 확인",
        "mock_store/random 아래 생성 샘플을 모두 삭제합니다. 계속할까요?"
      );
      if (!ok) return;
      try {
        const { res, body } = await getJson("/admin/mock-store/delete", { method: "POST" });
        if (!res.ok) {
          $("detailOut").textContent = pretty({ status: res.status, body });
          return;
        }
        $("detailOut").textContent = pretty({ status: res.status, body });
        $("imagesList").innerHTML = '<span class="warn">샘플이 삭제되었습니다.</span>';
        $("imageKv").innerHTML = '<div class="k">상태</div><div class="warn">샘플 없음</div>';
        $("folderList").innerHTML = '<span class="warn">생성된 파일이 없습니다.</span>';
        await callImages();
        await refreshStatus();
      } catch (e) {
        $("detailOut").textContent = pretty({ error: String(e) });
      }
    }

    function resetFilters() {
      $("sensor").value = "";
      $("level").value = "";
      $("fmt").value = "";
      $("q").value = "";
      callImages();
    }

    async function callImages() {
      const qs = buildQuery({
        sensor: $("sensor").value,
        level: $("level").value,
        fmt: $("fmt").value,
        q: $("q").value
      });
      const url = "/images" + (qs ? ("?" + qs) : "");
      try {
        const { body } = await getJson(url);
        const items = body.items || [];
        updateStats(items);
        renderImagesList(items);
      } catch (e) {
        $("imagesList").innerHTML = `<span class="warn">목록 조회 실패: ${String(e)}</span>`;
      }
    }

    async function callDetail() {
      const pid = $("pid").value.trim();
      if (!pid) {
        $("detailOut").textContent = pretty({ error: "image_id required" });
        return;
      }
      try {
        const { res, body } = await getJson(`/images/${encodeURIComponent(pid)}`);
        $("detailOut").textContent = pretty({ status: res.status, body });
        if (res.ok) renderSelectedImage(body);
      } catch (e) {
        $("detailOut").textContent = pretty({ error: String(e) });
      }
    }

    async function callDownload() {
      const pid = $("pid").value.trim();
      if (!pid) {
        $("detailOut").textContent = pretty({ error: "image_id required" });
        return;
      }
      const url = `/images/${encodeURIComponent(pid)}/download`;
      try {
        const res = await fetch(url);
        if (!res.ok) {
          const text = await res.text();
          $("detailOut").textContent = pretty({ status: res.status, error: text });
          return;
        }
        const blob = await res.blob();
        const link = document.createElement("a");
        const href = URL.createObjectURL(blob);
        link.href = href;
        const cd = res.headers.get("content-disposition") || "";
        const m = cd.match(/filename="?([^"]+)"?/);
        link.download = m ? m[1] : `${pid}.bin`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(href);
        $("detailOut").textContent = pretty({
          status: res.status,
          downloaded_bytes: blob.size,
          filename: link.download,
          endpoint: url
        });
      } catch (e) {
        $("detailOut").textContent = pretty({ error: String(e), endpoint: url });
      }
    }

    async function generateOsmImages() {
      const lat = Number($("osmLat").value);
      const lon = Number($("osmLon").value);
      const zoom = Number($("osmZoom").value);
      const sensor = $("osmSensor").value;
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(zoom)) {
        $("osmOut").textContent = pretty({ error: "latitude/longitude/zoom 값을 확인해주세요." });
        return;
      }
      if (jobRunning) return;
      openJobModal("OSM 샘플 생성 중", "OSM 기반 L0~L4 샘플을 생성하고 있습니다. 완료되면 닫기 버튼이 활성화됩니다.");
      $("osmGenerateBtn").disabled = true;
      $("osmHealthBanner").textContent = "OSM 타일 조회 및 생성 중...";
      try {
        const qs = buildQuery({ lat, lon, zoom, sensor });
        const url = `/osm/images/generate-all?${qs}`;
        const { res, body } = await getJson(url, { method: "POST" });
        $("osmOut").textContent = pretty({ status: res.status, body });
        if (!res.ok) {
          $("osmHealthBanner").innerHTML = `<span class="warn">OSM 생성 실패: ${res.status}</span>`;
          renderOsmList([]);
          updateOsmStats([]);
          const reason = body && body.detail ? String(body.detail) : `OSM 생성 실패(${res.status})`;
          finishJobModal(false, reason);
          return;
        }
        osmRequestId = body.request_id || "";
        osmItems = body.items || [];
        updateOsmStats(osmItems);
        $("osmHealthBanner").textContent = `OSM 상태: latest=${osmRequestId} / tile z${body.source?.zoom} (${body.source?.tile_x},${body.source?.tile_y}) / 이미지 ${osmItems.length}건`;
        await callOsmImages();
        await loadOsmStoreInfo();
        finishJobModal(true, "OSM 샘플 생성이 완료되었습니다. 확인 후 닫기를 누르세요.");
      } catch (e) {
        $("osmOut").textContent = pretty({ error: String(e) });
        $("osmHealthBanner").innerHTML = `<span class="warn">OSM 생성 실패: ${String(e)}</span>`;
        finishJobModal(false, `OSM 생성 중 오류가 발생했습니다: ${String(e)}`);
      } finally {
        $("osmGenerateBtn").disabled = false;
      }
    }

    async function deleteOsmSamples() {
      const ok = await openDeleteConfirm(
        "OSM 샘플 삭제 확인",
        "mock_store/osm 아래 생성 샘플을 모두 삭제합니다. 계속할까요?"
      );
      if (!ok) return;
      try {
        const { res, body } = await getJson("/admin/osm-store/delete", { method: "POST" });
        $("osmOut").textContent = pretty({ status: res.status, body });
        if (!res.ok) {
          $("osmHealthBanner").innerHTML = `<span class="warn">OSM 삭제 실패: ${res.status}</span>`;
          return;
        }
        osmItems = [];
        osmSelected = null;
        osmRequestId = "";
        updateOsmStats([]);
        renderOsmList([]);
        $("osmImageKv").innerHTML = '<div class="k">상태</div><div class="warn">OSM 샘플 없음</div>';
        $("osmFolderList").innerHTML = '<span class="warn">생성된 OSM 파일이 없습니다.</span>';
        $("osmHealthBanner").textContent = "OSM 상태: 생성된 이미지 없음";
        await loadOsmStoreInfo();
      } catch (e) {
        $("osmOut").textContent = pretty({ error: String(e) });
        $("osmHealthBanner").innerHTML = `<span class="warn">OSM 삭제 실패: ${String(e)}</span>`;
      }
    }

    async function downloadSelectedOsm() {
      if (!osmSelected || !osmSelected.download_url) {
        $("osmOut").textContent = pretty({ error: "다운로드할 OSM 이미지를 먼저 선택해주세요." });
        return;
      }
      const url = osmSelected.download_url;
      try {
        const res = await fetch(url);
        if (!res.ok) {
          const text = await res.text();
          $("osmOut").textContent = pretty({ status: res.status, error: text, endpoint: url });
          return;
        }
        const blob = await res.blob();
        const link = document.createElement("a");
        const href = URL.createObjectURL(blob);
        link.href = href;
        const cd = res.headers.get("content-disposition") || "";
        const m = cd.match(/filename="?([^"]+)"?/);
        link.download = m ? m[1] : (osmSelected.file_name || `${osmSelected.image_id}.bin`);
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(href);
        $("osmOut").textContent = pretty({
          status: res.status,
          downloaded_bytes: blob.size,
          filename: link.download,
          endpoint: url
        });
      } catch (e) {
        $("osmOut").textContent = pretty({ error: String(e), endpoint: url });
      }
    }

    async function loadOsmLatest() {
      try {
        const { res, body } = await getJson("/osm/images");
        if (!res.ok) {
          $("osmHealthBanner").innerHTML = `<span class="warn">OSM 목록 조회 실패: ${res.status}</span>`;
          return;
        }
        const latest = body.latest;
        if (!latest || !latest.items || !latest.items.length) {
          updateOsmStats([]);
          $("osmHealthBanner").textContent = `OSM 상태: 요청 ${body.request_count || 0}건 / 생성된 이미지 없음`;
          renderOsmList([]);
          return;
        }
        osmRequestId = latest.request_id || "";
        osmItems = latest.items || [];
        updateOsmStats(osmItems);
        const src = latest.source || {};
        $("osmHealthBanner").textContent = `OSM 상태: 요청 ${body.request_count || 0}건 / 최신 ${osmRequestId} / tile z${src.zoom} (${src.tile_x},${src.tile_y}) / 이미지 ${osmItems.length}건`;
        renderOsmList(osmItems);
      } catch (e) {
        updateOsmStats([]);
        $("osmHealthBanner").innerHTML = `<span class="warn">OSM 목록 조회 실패: ${String(e)}</span>`;
      }
    }

    async function loadOsmStoreInfo() {
      try {
        const { res, body } = await getJson("/admin/osm-store/info");
        if (!res.ok) {
          $("osmAdminStatus").innerHTML = `<span class="warn">OSM 스토어 조회 실패: ${res.status}</span>`;
          return;
        }
        const files = body.image_files || [];
        const folders = body.image_folders || [];
        $("osmAdminStatus").textContent = `스토어: ${toMockStoreRelative(body.store_dir)} / 요청 ${body.request_count || 0}건 / 최신 ${body.latest_request_id || "-"} / 폴더 ${folders.length}개 / 파일 ${files.length}개`;
        if (!files.length) {
          $("osmFolderList").innerHTML = '<span class="warn">생성된 OSM 파일이 없습니다.</span>';
          return;
        }
        $("osmFolderList").innerHTML = files.map((f) => `<div class="folder-item">${f}</div>`).join("");
      } catch (e) {
        $("osmAdminStatus").innerHTML = `<span class="warn">OSM 스토어 조회 실패: ${String(e)}</span>`;
      }
    }

    function resetOsmFilters() {
      const ids = ["osmFilterSensor", "osmFilterLevel", "osmFilterFmt", "osmFilterQ"];
      ids.forEach((id) => {
        const el = $(id);
        if (el) el.value = "";
      });
      callOsmImages();
    }

    async function callOsmImages() {
      const qs = buildQuery({
        sensor: $("osmFilterSensor")?.value,
        level: $("osmFilterLevel")?.value,
        fmt: $("osmFilterFmt")?.value,
        q: $("osmFilterQ")?.value,
      });
      const url = "/osm/images/items" + (qs ? ("?" + qs) : "");
      try {
        const { res, body } = await getJson(url);
        $("osmOut").textContent = pretty({ status: res.status, body });
        if (!res.ok) {
          $("osmImagesList").innerHTML = `<span class="warn">OSM 목록 조회 실패: ${res.status}</span>`;
          updateOsmStats([]);
          return;
        }
        const items = body.items || [];
        osmItems = items;
        if (items.length > 0) {
          osmRequestId = items[0].request_id || "";
        }
        renderOsmList(items);
        updateOsmStats(items);
      } catch (e) {
        $("osmOut").textContent = pretty({ error: String(e), endpoint: url });
        $("osmImagesList").innerHTML = `<span class="warn">OSM 목록 조회 실패: ${String(e)}</span>`;
        updateOsmStats([]);
      }
    }

    async function refreshOsmStatus() {
      await Promise.all([loadOsmLatest(), loadOsmStoreInfo()]);
      await callOsmImages();
    }

    function initPage() {
      try {
        renderLevelGuide();
        refreshStatus();
        renderOsmSelected(null);
        updateOsmStats([]);
        refreshOsmStatus();
        ["sensor", "level", "fmt"].forEach((id) => {
          const el = $(id);
          if (el) el.addEventListener("change", callImages);
        });
        ["osmFilterSensor", "osmFilterLevel", "osmFilterFmt"].forEach((id) => {
          const el = $(id);
          if (el) el.addEventListener("change", callOsmImages);
        });
        const krPreset = $("osmPresetKR");
        const kpPreset = $("osmPresetKP");
        if (krPreset) {
          krPreset.addEventListener("change", () => {
            applyOsmPreset(krPreset.value);
            if (kpPreset) kpPreset.value = "";
          });
        }
        if (kpPreset) {
          kpPreset.addEventListener("change", () => {
            applyOsmPreset(kpPreset.value);
            if (krPreset) krPreset.value = "";
          });
        }
        const latInput = $("osmLat");
        const lonInput = $("osmLon");
        [latInput, lonInput].forEach((el) => {
          if (!el) return;
          el.addEventListener("input", clearOsmPresetSelections);
          el.addEventListener("change", clearOsmPresetSelections);
        });
        callImages();
      } catch (e) {
        const msg = `UI 초기화 실패: ${String(e)}`;
        const admin = $("osmAdminStatus");
        if (admin) admin.innerHTML = `<span class="warn">${msg}</span>`;
      }
    }

    // Ensure inline onclick handlers always resolve, even if browser/global scoping differs.
    window.refreshStatus = refreshStatus;
    window.rebuildSamples = rebuildSamples;
    window.deleteSamples = deleteSamples;
    window.resetFilters = resetFilters;
    window.callImages = callImages;
    window.callDetail = callDetail;
    window.callDownload = callDownload;
    window.generateOsmImages = generateOsmImages;
    window.deleteOsmSamples = deleteOsmSamples;
    window.downloadSelectedOsm = downloadSelectedOsm;
    window.refreshOsmStatus = refreshOsmStatus;
    window.callOsmImages = callOsmImages;
    window.resetOsmFilters = resetOsmFilters;
    window.closeJobModal = closeJobModal;
    window.resolveDeleteConfirm = resolveDeleteConfirm;

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initPage);
    } else {
      initPage();
    }
  
