// web/static/app.js

(() => {
  "use strict";

  const POLL_INTERVAL_MS = 1000;

  const state = {
    availableCctvs: [],
    cameras: new Map(), // cam_id -> { element, canvas, ctx, isEditing, draftPoints, savedRoi }
    isPolling: false,
  };

  const dom = {
    searchInput: document.getElementById("cctv-search-input"),
    datalist: document.getElementById("cctv-options"),
    btnRefresh: document.getElementById("btn-refresh-cctvs"),
    btnAdd: document.getElementById("btn-add-cctv"),
    alertBanner: document.getElementById("alert-banner"),
    emptyState: document.getElementById("empty-state"),
    quickPicks: document.getElementById("quick-picks"),
    cameraGrid: document.getElementById("camera-grid"),
    kpiActiveCams: document.getElementById("kpi-active-cams"),
    kpiAlertPill: document.getElementById("kpi-alert-pill"),
    kpiHighQueue: document.getElementById("kpi-high-queue"),
    kpiTotalVehicles: document.getElementById("kpi-total-vehicles"),
  };

  let alertTimer = null;

  function showAlert(message, type = "error") {
    if (alertTimer) {
      clearTimeout(alertTimer);
    }
    dom.alertBanner.textContent = message;
    dom.alertBanner.className = `alert-banner ${type}`;

    alertTimer = setTimeout(() => {
      dom.alertBanner.classList.add("hidden");
    }, 6000);
  }

  async function apiRequest(url, options = {}) {
    const response = await fetch(url, options);
    let data = null;

    try {
      data = await response.json();
    } catch (_) {
      throw new Error(`Respons server tidak valid (HTTP ${response.status}).`);
    }

    if (!response.ok || !data || data.ok === false) {
      const errorMessage =
        (data && data.error) || `Permintaan gagal (HTTP ${response.status}).`;
      throw new Error(errorMessage);
    }

    return data;
  }

  function renderCctvOptions(cctvs) {
    dom.datalist.innerHTML = "";
    const fragment = document.createDocumentFragment();

    cctvs.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      fragment.appendChild(opt);
    });

    dom.datalist.appendChild(fragment);

    // Tampilkan beberapa tombol cepat pada layar kosong awal.
    dom.quickPicks.innerHTML = "";
    cctvs.slice(0, 5).forEach((name) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-secondary btn-sm";
      btn.textContent = `+ ${name}`;
      btn.addEventListener("click", () => addCameraByName(name));
      dom.quickPicks.appendChild(btn);
    });
  }

  async function loadAvailableCctvs(forceRefresh = false) {
    dom.btnRefresh.disabled = true;
    try {
      const suffix = forceRefresh ? "?refresh=1" : "";
      const data = await apiRequest(`/api/cctvs${suffix}`);
      state.availableCctvs = data.cctvs || [];
      renderCctvOptions(state.availableCctvs);

      if (forceRefresh) {
        showAlert(
          `Daftar CCTV diperbarui (${state.availableCctvs.length} lokasi tersedia).`,
          "success"
        );
      }
    } catch (err) {
      showAlert(err.message, "error");
    } finally {
      dom.btnRefresh.disabled = false;
    }
  }

  async function addCameraByName(rawName) {
    const ownerName = (rawName || "").trim();
    if (!ownerName) {
      showAlert("Silakan pilih atau ketik nama lokasi CCTV terlebih dahulu.", "error");
      return;
    }

    dom.btnAdd.disabled = true;
    try {
      await apiRequest("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner_name: ownerName }),
      });

      dom.searchInput.value = "";
      showAlert(
        `CCTV "${ownerName}" berhasil ditambahkan. Klik "Edit ROI" untuk menentukan zona antrean.`,
        "success"
      );
      await pollCameras();
    } catch (err) {
      showAlert(err.message, "error");
    } finally {
      dom.btnAdd.disabled = false;
    }
  }

  async function removeCamera(camId, ownerName) {
    try {
      await apiRequest(`/api/cameras/${encodeURIComponent(camId)}`, {
        method: "DELETE",
      });
      showAlert(`Pemantauan "${ownerName}" dihentikan.`, "success");
      await pollCameras();
    } catch (err) {
      showAlert(err.message, "error");
    }
  }

  function resizeCanvasToDisplaySize(canvas) {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
  }

  function drawRoiOverlay(entry) {
    const { canvas, ctx, isEditing, draftPoints } = entry;
    resizeCanvasToDisplaySize(canvas);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Saat tidak dalam mode edit, video MJPEG sudah bersih atau menampilkan garis ROI tersimpan.
    if (!isEditing || draftPoints.length === 0) {
      return;
    }

    ctx.save();
    ctx.strokeStyle = "#38bdf8";
    ctx.fillStyle = "rgba(56, 189, 248, 0.22)";
    ctx.lineWidth = 2.5;

    ctx.beginPath();
    draftPoints.forEach(([nx, ny], idx) => {
      const px = nx * canvas.width;
      const py = ny * canvas.height;
      if (idx === 0) {
        ctx.moveTo(px, py);
      } else {
        ctx.lineTo(px, py);
      }
    });

    if (draftPoints.length >= 3) {
      ctx.closePath();
      ctx.fill();
    }
    ctx.stroke();

    // Gambar titik sudut (vertex) agar mudah dilihat saat mengklik.
    draftPoints.forEach(([nx, ny], idx) => {
      const px = nx * canvas.width;
      const py = ny * canvas.height;
      ctx.beginPath();
      ctx.arc(px, py, 5, 0, Math.PI * 2);
      ctx.fillStyle = idx === 0 ? "#22c55e" : "#facc15";
      ctx.fill();
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });

    ctx.restore();
  }

  function syncToolbarButtons(entry) {
    const hasSavedRoi = Array.isArray(entry.savedRoi) && entry.savedRoi.length >= 3;

    entry.canvas.classList.toggle("editing", entry.isEditing);
    entry.refs.roiHint.classList.toggle("hidden", !entry.isEditing);

    entry.refs.btnEditRoi.classList.toggle("hidden", entry.isEditing);
    entry.refs.btnUndoRoi.classList.toggle("hidden", !entry.isEditing);
    entry.refs.btnSaveRoi.classList.toggle("hidden", !entry.isEditing);
    entry.refs.btnCancelRoi.classList.toggle("hidden", !entry.isEditing);

    entry.refs.btnUndoRoi.disabled = entry.draftPoints.length === 0;
    entry.refs.btnSaveRoi.disabled = entry.draftPoints.length < 3;
    entry.refs.btnResetRoi.disabled = entry.isEditing || !hasSavedRoi;
  }

  function setEditMode(entry, enabled) {
    entry.isEditing = enabled;
    entry.draftPoints = [];
    syncToolbarButtons(entry);
    drawRoiOverlay(entry);
  }

  async function saveRoi(camId, entry) {
    if (entry.draftPoints.length < 3) {
      showAlert("Polygon ROI minimal membutuhkan 3 titik sudut.", "error");
      return;
    }

    entry.refs.btnSaveRoi.disabled = true;
    try {
      const data = await apiRequest(
        `/api/cameras/${encodeURIComponent(camId)}/roi`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ points: entry.draftPoints }),
        }
      );

      entry.savedRoi = data.roi_normalized || [];
      setEditMode(entry, false);
      showAlert("Area ROI baru berhasil diterapkan pada stream.", "success");
      await pollCameras();
    } catch (err) {
      showAlert(err.message, "error");
      syncToolbarButtons(entry);
    }
  }

  async function resetRoi(camId, entry) {
    entry.refs.btnResetRoi.disabled = true;
    try {
      const data = await apiRequest(
        `/api/cameras/${encodeURIComponent(camId)}/roi/reset`,
        { method: "POST" }
      );
      entry.savedRoi = data.roi_normalized || [];
      setEditMode(entry, false);
      showAlert("Area ROI dihapus. Video stream kembali bersih.", "success");
      await pollCameras();
    } catch (err) {
      showAlert(err.message, "error");
      syncToolbarButtons(entry);
    }
  }

  function createCameraCard(cam) {
    const card = document.createElement("article");
    card.className = "camera-card";
    card.dataset.camId = cam.cam_id;

    // Header kartu
    const header = document.createElement("div");
    header.className = "card-header";

    const titleWrap = document.createElement("div");
    titleWrap.className = "card-title-wrap";

    const title = document.createElement("h3");
    title.textContent = cam.owner_name;

    const streamStatus = document.createElement("span");
    streamStatus.className = "stream-status";
    streamStatus.textContent = cam.stream_status || "Menghubungkan...";

    titleWrap.appendChild(title);
    titleWrap.appendChild(streamStatus);

    const btnStop = document.createElement("button");
    btnStop.type = "button";
    btnStop.className = "btn btn-danger btn-sm";
    btnStop.textContent = "Hentikan";
    btnStop.addEventListener("click", () =>
      removeCamera(cam.cam_id, cam.owner_name)
    );

    header.appendChild(titleWrap);
    header.appendChild(btnStop);

    // Stage video + canvas ROI
    const stage = document.createElement("div");
    stage.className = "video-stage";

    const img = document.createElement("img");
    img.className = "video-feed";
    img.src = `/video_feed/${encodeURIComponent(cam.cam_id)}`;
    img.alt = `Live CCTV ${cam.owner_name}`;

    const canvas = document.createElement("canvas");
    canvas.className = "roi-canvas";

    const roiHint = document.createElement("div");
    roiHint.className = "roi-hint hidden";
    roiHint.textContent =
      "Mode Gambar ROI: Klik titik sudut area lajur antrean (min. 3 titik), lalu klik Simpan ROI.";

    stage.appendChild(img);
    stage.appendChild(canvas);
    stage.appendChild(roiHint);

    // BARIS 1 SETELAH FRAME: Keterangan status volume kendaraan di posisi tengah (center)
    const statusCaptionBar = document.createElement("div");
    statusCaptionBar.className = "status-caption-bar";

    const trafficBadge = document.createElement("span");
    trafficBadge.className = "traffic-badge neutral";
    trafficBadge.textContent = "ROI BELUM DIATUR";
    statusCaptionBar.appendChild(trafficBadge);

    // BARIS 2 SETELAH CAPTION: Tombol pengaturan ROI dengan posisi statis
    const roiControlsBar = document.createElement("div");
    roiControlsBar.className = "roi-controls-bar";

    const btnEditRoi = document.createElement("button");
    btnEditRoi.type = "button";
    btnEditRoi.className = "btn btn-secondary btn-sm";
    btnEditRoi.textContent = "Edit ROI";

    const btnUndoRoi = document.createElement("button");
    btnUndoRoi.type = "button";
    btnUndoRoi.className = "btn btn-secondary btn-sm hidden";
    btnUndoRoi.textContent = "Undo Titik";

    const btnSaveRoi = document.createElement("button");
    btnSaveRoi.type = "button";
    btnSaveRoi.className = "btn btn-success btn-sm hidden";
    btnSaveRoi.textContent = "Simpan ROI";

    const btnCancelRoi = document.createElement("button");
    btnCancelRoi.type = "button";
    btnCancelRoi.className = "btn btn-secondary btn-sm hidden";
    btnCancelRoi.textContent = "Batal";

    const btnResetRoi = document.createElement("button");
    btnResetRoi.type = "button";
    btnResetRoi.className = "btn btn-secondary btn-sm";
    btnResetRoi.textContent = "Reset ROI";

    roiControlsBar.append(
      btnEditRoi,
      btnUndoRoi,
      btnSaveRoi,
      btnCancelRoi,
      btnResetRoi
    );

    // Panel metrik
    const metricsBody = document.createElement("div");
    metricsBody.className = "metrics-body";

    metricsBody.innerHTML = `
      <div class="metrics-grid">
        <div class="metric-box">
          <span>Antrean (ROI)</span>
          <strong data-field="queue">0</strong>
        </div>
        <div class="metric-box">
          <span>Berhenti</span>
          <strong data-field="stopped">0</strong>
        </div>
        <div class="metric-box">
          <span>Rata-rata Tunggu</span>
          <strong data-field="wait">0.0s</strong>
        </div>
        <div class="metric-box">
          <span>Skor Bobot</span>
          <strong data-field="score">0</strong>
        </div>
      </div>
      <div class="class-breakdown">
        <span class="class-chip">Mobil: <strong data-cls="car">0</strong></span>
        <span class="class-chip">Motor: <strong data-cls="motorcycle">0</strong></span>
        <span class="class-chip">Bus: <strong data-cls="bus">0</strong></span>
        <span class="class-chip">Truk: <strong data-cls="truck">0</strong></span>
      </div>
    `;

    card.append(header, stage, statusCaptionBar, roiControlsBar, metricsBody);

    const entry = {
      element: card,
      canvas,
      ctx: canvas.getContext("2d"),
      isEditing: false,
      draftPoints: [],
      savedRoi: cam.roi_normalized || [],
      refs: {
        streamStatus,
        trafficBadge,
        roiHint,
        btnEditRoi,
        btnUndoRoi,
        btnSaveRoi,
        btnCancelRoi,
        btnResetRoi,
        queue: metricsBody.querySelector('[data-field="queue"]'),
        stopped: metricsBody.querySelector('[data-field="stopped"]'),
        wait: metricsBody.querySelector('[data-field="wait"]'),
        score: metricsBody.querySelector('[data-field="score"]'),
        car: metricsBody.querySelector('[data-cls="car"]'),
        motorcycle: metricsBody.querySelector('[data-cls="motorcycle"]'),
        bus: metricsBody.querySelector('[data-cls="bus"]'),
        truck: metricsBody.querySelector('[data-cls="truck"]'),
      },
    };

    // Event klik kanvas untuk mencatat koordinat ternormalisasi [0.0..1.0]
    canvas.addEventListener("click", (event) => {
      if (!entry.isEditing) {
        return;
      }
      const rect = canvas.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) {
        return;
      }
      const nx = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      const ny = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
      entry.draftPoints.push([Number(nx.toFixed(4)), Number(ny.toFixed(4))]);
      syncToolbarButtons(entry);
      drawRoiOverlay(entry);
    });

    btnEditRoi.addEventListener("click", () => setEditMode(entry, true));
    btnUndoRoi.addEventListener("click", () => {
      entry.draftPoints.pop();
      syncToolbarButtons(entry);
      drawRoiOverlay(entry);
    });
    btnSaveRoi.addEventListener("click", () => saveRoi(cam.cam_id, entry));
    btnCancelRoi.addEventListener("click", () => setEditMode(entry, false));
    btnResetRoi.addEventListener("click", () => resetRoi(cam.cam_id, entry));

    window.addEventListener("resize", () => drawRoiOverlay(entry));
    syncToolbarButtons(entry);

    return entry;
  }

  function updateCameraCard(entry, cam) {
    const metrics = cam.metrics || {};
    const classes = metrics.class_counts || {};
    const statusText = metrics.status || "ROI BELUM DIATUR";
    const isUnsetRoi = statusText === "ROI BELUM DIATUR" || metrics.has_roi === false;
    const isHighQueue = statusText === "INDIKASI ANTREAN TINGGI";
    const isWarning = statusText.startsWith("BERJALAN");

    entry.refs.streamStatus.textContent = cam.stream_status || "-";
    entry.refs.queue.textContent = String(metrics.queue_count ?? 0);
    entry.refs.stopped.textContent = String(metrics.stopped_count ?? 0);
    entry.refs.wait.textContent = `${Number(
      metrics.average_stopped_seconds ?? 0
    ).toFixed(1)}s`;
    entry.refs.score.textContent = String(metrics.weighted_score ?? 0);

    entry.refs.car.textContent = String(classes.car ?? 0);
    entry.refs.motorcycle.textContent = String(classes.motorcycle ?? 0);
    entry.refs.bus.textContent = String(classes.bus ?? 0);
    entry.refs.truck.textContent = String(classes.truck ?? 0);

    entry.refs.trafficBadge.textContent = statusText;
    entry.refs.trafficBadge.className = "traffic-badge";
    if (isUnsetRoi) {
      entry.refs.trafficBadge.classList.add("neutral");
    } else if (isHighQueue) {
      entry.refs.trafficBadge.classList.add("danger");
    } else if (isWarning) {
      entry.refs.trafficBadge.classList.add("warning");
    }

    entry.element.classList.toggle("high-queue", isHighQueue);
    entry.savedRoi = cam.roi_normalized || [];
    syncToolbarButtons(entry);
  }

  async function pollCameras() {
    if (state.isPolling) {
      return;
    }
    state.isPolling = true;

    try {
      const data = await apiRequest("/api/cameras");
      const activeList = data.cameras || [];
      const activeIds = new Set(activeList.map((c) => c.cam_id));

      // Hapus kartu kamera yang sudah dihentikan.
      for (const [camId, entry] of state.cameras.entries()) {
        if (!activeIds.has(camId)) {
          entry.element.remove();
          state.cameras.delete(camId);
        }
      }

      let highQueueCount = 0;
      let totalVehiclesInRoi = 0;

      // Tambah kartu baru atau perbarui metrik kartu eksisting tanpa reload video.
      activeList.forEach((cam) => {
        let entry = state.cameras.get(cam.cam_id);
        if (!entry) {
          entry = createCameraCard(cam);
          state.cameras.set(cam.cam_id, entry);
          dom.cameraGrid.appendChild(entry.element);
        }
        updateCameraCard(entry, cam);

        const m = cam.metrics || {};
        if (m.status === "INDIKASI ANTREAN TINGGI") {
          highQueueCount += 1;
        }
        totalVehiclesInRoi += Number(m.queue_count ?? 0);
      });

      // Perbarui KPI global
      dom.kpiActiveCams.textContent = `${data.active_count ?? 0} / ${
        data.max_cameras ?? 4
      }`;
      dom.kpiHighQueue.textContent = `${highQueueCount} Titik`;
      dom.kpiAlertPill.classList.toggle("pill-alert", highQueueCount > 0);
      dom.kpiTotalVehicles.textContent = String(totalVehiclesInRoi);

      dom.emptyState.classList.toggle("hidden", activeList.length > 0);
    } catch (_) {
      // Hindari spam notifikasi saat gangguan jaringan sesaat pada polling rutin.
    } finally {
      state.isPolling = false;
    }
  }

  function bindEvents() {
    dom.btnRefresh.addEventListener("click", () => loadAvailableCctvs(true));
    dom.btnAdd.addEventListener("click", () =>
      addCameraByName(dom.searchInput.value)
    );
    dom.searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addCameraByName(dom.searchInput.value);
      }
    });
  }

  async function init() {
    bindEvents();
    await loadAvailableCctvs(false);
    await pollCameras();
    setInterval(pollCameras, POLL_INTERVAL_MS);
  }

  document.addEventListener("DOMContentLoaded", init);
})();