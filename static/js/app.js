document.addEventListener('DOMContentLoaded', () => {
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

  const $ = id => document.getElementById(id);

  // ===== DOM REFS =====
  const fileInput         = $('fileInput');
  const btnUploadNew      = $('btnUploadNew');
  const btnDownload       = $('btnDownload');
  const loadingOverlay    = $('loadingOverlay');
  const loadingMsg        = $('loadingMsg');
  const ownershipModal    = $('ownershipModal');
  const chkOwnership      = $('chkOwnership');
  const btnCancelUpload   = $('btnCancelUpload');
  const btnConfirmUpload  = $('btnConfirmUpload');
  const btnProcess        = $('btnProcess');
  const btnResetAll       = $('btnResetAll');

  const selMode           = $('selMode');
  const chkAutoWatermark  = $('chkAutoWatermark');
  const chkAutoTeacher    = $('chkAutoTeacher');
  const chkAutoFooter     = $('chkAutoFooter');
  const chkAutoAd         = $('chkAutoAd');

  const selStrength       = $('selStrength');
  const selFillMethod     = $('selFillMethod');
  const chkPreserveFG     = $('chkPreserveForeground');
  const selExportQuality  = $('selExportQuality');

  const sectionCleanup    = $('sectionCleanup');
  const sectionManual     = $('sectionManual');
  const selApplyScope     = $('selApplyScope');
  const inPageRange       = $('inPageRange');

  // Manual tools
  const btnToolPan        = $('btnToolPan');
  const btnToolRect       = $('btnToolRect');
  const btnToolBrush      = $('btnToolBrush');
  const rngBrushSize      = $('rngBrushSize');
  const btnUndo           = $('btnUndo');
  const btnRedo           = $('btnRedo');
  const btnResetPage      = $('btnResetPage');

  const toastContainer    = $('toastContainer');
  const originalPages     = $('originalPages');
  const generatedPages    = $('generatedPages');

  // ===== STATE =====
  const appState = {
    fileId: null,
    pageCount: 0,
    originalSizeMb: 0,
    uploadReady: false,
    processedReady: false
  };

  let pendingFile     = null;
  let debounceTimer   = null;
  let currentPageNum  = 1;
  let originalPdfDoc  = null;

  let activeTool     = "pan"; 
  let isDrawing      = false;
  let currentStroke  = [];
  let rectStart      = null;
  let rectCurrent    = null;

  // ===== TOAST NOTIFICATIONS =====
  function showToast(message, type = "error") {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon">${type === 'error' ? '⚠️' : '✅'}</span> <span class="toast-msg">${message}</span>`;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // ===== SAFE JSON RESPONSE =====
  async function safeJsonResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok) {
      let message = `Request failed with status ${response.status}`;
      if (contentType.includes("application/json")) {
        try {
          const err = await response.json();
          message = err.message || err.error || message;
        } catch (_) {}
      } else {
        const text = await response.text();
        if (text.includes("Request Entity Too Large") || text.includes("FUNCTION_PAYLOAD_TOO_LARGE")) {
          message = "File is too large for Vercel upload. Please compress the PDF or use a smaller file.";
        } else {
          message = text.slice(0, 200) || message;
        }
      }
      throw new Error(message);
    }
    if (!contentType.includes("application/json")) {
      const text = await response.text();
      throw new Error("Server returned non-JSON response: " + text.slice(0, 120));
    }
    return await response.json();
  }

  // ===== MODE SWITCHING =====
  selMode.addEventListener('change', () => {
    const mode = selMode.value;
    sectionCleanup.style.display = (mode === 'visual-cleanup' || mode === 'auto-background') ? 'block' : 'none';
    sectionManual.style.display  = (mode === 'manual-erase') ? 'block' : 'none';
  });

  selApplyScope.addEventListener('change', () => {
    inPageRange.style.display = (selApplyScope.value === 'range') ? 'block' : 'none';
  });

  // ===== TOOL SELECTION =====
  function setActiveTool(tool) {
    activeTool = tool;
    btnToolPan.classList.toggle('active', tool === 'pan');
    btnToolRect.classList.toggle('active', tool === 'rectangle');
    btnToolBrush.classList.toggle('active', tool === 'brush');
    
    // Update pointer events on all overlays
    document.querySelectorAll(".tool-overlay").forEach(overlay => {
        overlay.style.pointerEvents = (tool === "pan") ? "none" : "auto";
    });
  }

  btnToolPan.addEventListener('click', () => setActiveTool('pan'));
  btnToolRect.addEventListener('click', () => setActiveTool('rectangle'));
  btnToolBrush.addEventListener('click', () => setActiveTool('brush'));

  // ===== OWNERSHIP MODAL =====
  btnUploadNew.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', e => {
    if (e.target.files.length > 0) {
      pendingFile = e.target.files[0];
      const MAX_UPLOAD_MB = 4.4;
      if (pendingFile.size > MAX_UPLOAD_MB * 1024 * 1024) {
        showToast(`Maximum upload size is 4.4MB on this deployed version. Please compress the PDF or upload a smaller file.`, "error");
        fileInput.value = '';
        return;
      }
      chkOwnership.checked = false;
      btnConfirmUpload.disabled = true;
      ownershipModal.classList.add('active');
    }
    fileInput.value = '';
  });
  chkOwnership.addEventListener('change', () => {
    btnConfirmUpload.disabled = !chkOwnership.checked;
  });
  btnCancelUpload.addEventListener('click', () => {
    ownershipModal.classList.remove('active');
    pendingFile = null;
  });
  btnConfirmUpload.addEventListener('click', async () => {
    ownershipModal.classList.remove('active');
    if (pendingFile) await handleUpload(pendingFile);
  });

  // ===== UPLOAD & ORIGINAL PREVIEW =====
  async function handleUpload(file) {
    if (!file) return;

    if (file.size > 4.4 * 1024 * 1024) {
      showToast('File size is too large. Max size is 4.4MB.', 'error');
      $('fileInput').value = "";
      return;
    }

    try {
      showLoading('Uploading & analyzing document...');

      // 1. Client-Side Render Original Pages
      const objectUrl = URL.createObjectURL(file);
      await renderAllOriginalPages(objectUrl, file.type.startsWith('image/') ? 'image' : 'pdf');

      // 2. Upload to backend
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await safeJsonResponse(res);

      if (data.status === 'success') {
        appState.fileId = data.file_id;
        appState.pageCount = data.page_count;
        appState.originalSizeMb = data.original_size_mb || 0;
        appState.uploadReady = true;
        appState.processedReady = true;
        
        document.body.dataset.fileId = data.file_id;
        localStorage.setItem("currentFileId", data.file_id);
        localStorage.setItem("currentPageCount", String(data.page_count));
        
        btnDownload.disabled = false;

        hideLoading();
        doLivePreview();
      } else {
        throw new Error(data.message || 'Upload failed');
      }
    } catch (err) {
      hideLoading();
      showToast(err.message, 'error');
    }
  }

  btnProcess.addEventListener('click', () => triggerLivePreview());

  function triggerLivePreview() {
    if (!appState.fileId) return;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => doLivePreview(), 400);
  }

  // ===== SCROLL PAGE TRACKER =====
  function setupScrollPageTracker(container, counterElement, totalPages) {
    const pages = container.querySelectorAll(".page-shell");
    const observer = new IntersectionObserver((entries) => {
      let mostVisible = null;
      let maxRatio = 0;

      entries.forEach(entry => {
        if (entry.intersectionRatio > maxRatio) {
          maxRatio = entry.intersectionRatio;
          mostVisible = entry.target;
        }
      });

      if (mostVisible) {
        const page = mostVisible.dataset.page;
        counterElement.textContent = `Page ${page} / ${totalPages}`;
        container.dataset.currentPage = page;
      }
    }, {
      root: container,
      threshold: [0.25, 0.4, 0.55, 0.7, 0.85]
    });

    pages.forEach(page => observer.observe(page));
  }

  // ===== SYNCHRONIZED SCROLLING =====
  let isSyncingLeftScroll = false;
  let isSyncingRightScroll = false;

  originalPages.addEventListener("scroll", function() {
    if (!isSyncingLeftScroll) {
      isSyncingRightScroll = true;
      generatedPages.scrollTop = this.scrollTop;
    }
    isSyncingLeftScroll = false;
  });

  generatedPages.addEventListener("scroll", function() {
    if (!isSyncingRightScroll) {
      isSyncingLeftScroll = true;
      originalPages.scrollTop = this.scrollTop;
    }
    isSyncingRightScroll = false;
  });

  // ===== GENERATED PREVIEW SHOW =====
  function showGeneratedPreviewPanel() {
    const panel = document.querySelector(".generated-panel");
    const container = document.getElementById("generatedPages");

    panel.classList.remove("hidden");
    panel.style.display = "block";
    panel.style.visibility = "visible";
    panel.style.opacity = "1";

    container.classList.remove("hidden");
    container.style.display = "flex";
    container.style.visibility = "visible";
    container.style.opacity = "1";

    panel.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "nearest"
    });
  }

  // ===== RENDER ALL ORIGINAL PAGES =====
  async function renderAllOriginalPages(url, fmt) {
    const container = document.getElementById("originalPages");
    const counter = document.getElementById("originalScrollPage");

    if (fmt === 'image') {
      container.innerHTML = "";
      counter.textContent = "Page 1 / 1";
      const shell = document.createElement("div");
      shell.className = "page-shell original-page";
      shell.dataset.page = "1";
      const img = document.createElement("img");
      img.src = url;
      img.className = "pdf-page-canvas";
      shell.appendChild(img);
      container.appendChild(shell);
      return;
    }

    try {
      container.innerHTML = "";
      counter.textContent = "Loading...";

      originalPdfDoc = await pdfjsLib.getDocument(url).promise;
      appState.pageCount = originalPdfDoc.numPages;
      counter.textContent = `Page 1 / ${appState.pageCount}`;

      for (let pageNumber = 1; pageNumber <= appState.pageCount; pageNumber++) {
        const shell = document.createElement("div");
        shell.className = "page-shell original-page";
        shell.dataset.page = pageNumber;

        const canvas = document.createElement("canvas");
        canvas.className = "pdf-page-canvas";

        shell.appendChild(canvas);
        container.appendChild(shell);

        const page = await originalPdfDoc.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1.25 });
        const ctx = canvas.getContext("2d");

        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.style.width = "100%";
        canvas.style.height = "auto";

        await page.render({
          canvasContext: ctx,
          viewport: viewport
        }).promise;
      }

      setupScrollPageTracker(container, counter, appState.pageCount);
    } catch (err) {
      console.error(err);
      container.innerHTML = `<div class="preview-error">Failed to load original PDF preview.</div>`;
    }
  }

  function getSettingsString() {
    return encodeURIComponent(JSON.stringify({
      mode: selMode.value,
      auto_watermark: chkAutoWatermark.checked,
      auto_teacher: chkAutoTeacher.checked,
      auto_footer: chkAutoFooter.checked,
      auto_ad: chkAutoAd.checked,
      cleanup_strength: selStrength.value,
      fill_method: selFillMethod.value,
      preserve_foreground: chkPreserveFG.checked,
      apply_scope: selApplyScope ? selApplyScope.value : 'current',
      page_range: inPageRange ? inPageRange.value.trim() : ''
    }));
  }

  // ===== RENDER ALL GENERATED PAGES =====
  async function doLivePreview() {
    const fileId = appState.fileId || document.body.dataset.fileId || localStorage.getItem("currentFileId");
    if (!fileId) return;
    
    showLoading('Generating preview...');
    try {
      const container = document.getElementById("generatedPages");
      const counter = document.getElementById("generatedScrollPage");

      container.innerHTML = "";
      counter.textContent = `Page 1 / ${appState.pageCount}`;
      const settingsStr = getSettingsString();

      showGeneratedPreviewPanel();

      for (let pageNumber = 1; pageNumber <= appState.pageCount; pageNumber++) {
        const shell = document.createElement("div");
        shell.className = "page-shell generated-page";
        shell.dataset.page = pageNumber;

        const img = document.createElement("img");
        img.className = "generated-page-img";
        img.alt = `Generated page ${pageNumber}`;
        img.loading = "lazy";
        img.src = `/api/preview-page/${fileId}/${pageNumber}?settings=${settingsStr}&t=${Date.now()}`;

        const overlay = document.createElement("canvas");
        overlay.className = "tool-overlay";
        overlay.style.pointerEvents = (activeTool === "pan") ? "none" : "auto";

        img.onload = () => {
          shell.classList.add("loaded");
          syncOverlayCanvasSize(img, overlay);
          attachOverlayEvents(overlay);
        };

        img.onerror = () => {
          shell.innerHTML = `
            <div class="preview-error">
              Failed to load page ${pageNumber}
            </div>
          `;
        };

        shell.appendChild(img);
        shell.appendChild(overlay);
        container.appendChild(shell);
      }

      setupScrollPageTracker(container, counter, appState.pageCount);

    } catch (err) {
      showToast('Preview error: ' + err.message, 'error');
    } finally {
      hideLoading();
    }
  }

  // ===== DRAWING ENGINE (POINTER EVENTS) =====
  function syncOverlayCanvasSize(img, overlay) {
    overlay.style.width = img.clientWidth + "px";
    overlay.style.height = img.clientHeight + "px";
    overlay.width = img.naturalWidth;
    overlay.height = img.naturalHeight;
  }

  window.addEventListener('resize', () => {
    document.querySelectorAll(".generated-page").forEach(shell => {
      const img = shell.querySelector(".generated-page-img");
      const overlay = shell.querySelector(".tool-overlay");
      if (img && overlay) syncOverlayCanvasSize(img, overlay);
    });
  });

  function attachOverlayEvents(overlay) {
    overlay.addEventListener("pointerdown", handlePointerDown);
    overlay.addEventListener("pointermove", handlePointerMove);
    overlay.addEventListener("pointerup", handlePointerUp);
    overlay.addEventListener("pointercancel", handlePointerUp);
  }

  function getOverlayPoint(event, overlay) {
    const rect = overlay.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const scaleX = overlay.width / rect.width;
    const scaleY = overlay.height / rect.height;
    return { x: x * scaleX, y: y * scaleY };
  }

  function handlePointerDown(event) {
    if (activeTool === "pan") return;
    event.preventDefault();
    isDrawing = true;
    document.body.classList.add("drawing-active");
    
    const overlay = event.currentTarget;
    overlay.setPointerCapture(event.pointerId);

    if (activeTool === "brush") {
      currentStroke = [];
      const point = getOverlayPoint(event, overlay);
      currentStroke.push(point);
      drawBrushLine(overlay, currentStroke);
    } else if (activeTool === "rectangle") {
      rectStart = getOverlayPoint(event, overlay);
      rectCurrent = rectStart;
    }
  }

  function handlePointerMove(event) {
    if (!isDrawing) return;
    event.preventDefault();
    const overlay = event.currentTarget;
    
    if (activeTool === "brush") {
      const point = getOverlayPoint(event, overlay);
      currentStroke.push(point);
      drawBrushLine(overlay, currentStroke);
    } else if (activeTool === "rectangle") {
      rectCurrent = getOverlayPoint(event, overlay);
      drawRectanglePreview(overlay, rectStart, rectCurrent);
    }
  }

  async function handlePointerUp(event) {
    if (!isDrawing) return;
    event.preventDefault();
    isDrawing = false;
    document.body.classList.remove("drawing-active");

    const overlay = event.currentTarget;
    const pageShell = overlay.closest(".generated-page");
    const pageNumber = Number(pageShell.dataset.page);

    if (activeTool === "brush" && currentStroke.length > 0) {
      await sendBrushStrokeToBackend(pageNumber, currentStroke, rngBrushSize.value);
    } else if (activeTool === "rectangle" && rectStart) {
      const rect = normalizeRect(rectStart, rectCurrent);
      if (rect.width > 5 && rect.height > 5) {
        await sendRectangleToBackend(pageNumber, rect);
      }
      rectStart = null;
      rectCurrent = null;
    }
  }

  function normalizeRect(a, b) {
    return {
      x: Math.min(a.x, b.x),
      y: Math.min(a.y, b.y),
      width: Math.abs(a.x - b.x),
      height: Math.abs(a.y - b.y)
    };
  }

  function drawBrushLine(overlay, points) {
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    ctx.strokeStyle = 'rgba(239, 68, 68, 0.8)';
    ctx.lineWidth = parseInt(rngBrushSize.value);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.stroke();
  }

  function drawRectanglePreview(overlay, start, current) {
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    const rect = normalizeRect(start, current);
    
    ctx.fillStyle = 'rgba(239,68,68,0.25)';
    ctx.strokeStyle = 'rgba(239,68,68,0.8)';
    ctx.lineWidth = 2;
    ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
    ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
  }

  // ===== BACKEND ACTIONS =====
  async function sendBrushStrokeToBackend(pageNumber, points, size) {
    showLoading('Applying brush...');
    try {
      const res = await fetch('/api/apply-brush', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: appState.fileId,
          page: pageNumber,
          brush_size: size,
          points: points,
          fill_method: selFillMethod.value,
          preserve_foreground: chkPreserveFG.checked
        })
      });
      const data = await safeJsonResponse(res);
      refreshGeneratedPages(data.affected_pages || [pageNumber]);
    } catch (err) {
      showToast(err.message, 'error');
      // clear overlay
      const shell = document.querySelector(`.generated-page[data-page="${pageNumber}"]`);
      if (shell) {
        const overlay = shell.querySelector(".tool-overlay");
        overlay.getContext('2d').clearRect(0,0,overlay.width,overlay.height);
      }
    } finally {
      hideLoading();
    }
  }

  async function sendRectangleToBackend(pageNumber, rect) {
    showLoading('Applying rectangle cleanup...');
    try {
      const res = await fetch('/api/apply-rectangle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: appState.fileId,
          page: pageNumber,
          rect: rect,
          apply_mode: selApplyScope ? selApplyScope.value : 'current',
          page_range: inPageRange ? inPageRange.value.trim() : '',
          fill_method: selFillMethod.value,
          preserve_foreground: chkPreserveFG.checked
        })
      });
      const data = await safeJsonResponse(res);
      refreshGeneratedPages(data.affected_pages || [pageNumber]);
    } catch (err) {
      showToast(err.message, 'error');
      // clear overlay
      const shell = document.querySelector(`.generated-page[data-page="${pageNumber}"]`);
      if (shell) {
        const overlay = shell.querySelector(".tool-overlay");
        overlay.getContext('2d').clearRect(0,0,overlay.width,overlay.height);
      }
    } finally {
      hideLoading();
    }
  }

  function refreshGeneratedPages(pageNumbers) {
    const settingsStr = getSettingsString();
    pageNumbers.forEach(num => {
      const shell = document.querySelector(`.generated-page[data-page="${num}"]`);
      if (shell) {
        const img = shell.querySelector(".generated-page-img");
        const overlay = shell.querySelector(".tool-overlay");
        img.src = `/api/preview-page/${appState.fileId}/${num}?settings=${settingsStr}&t=${Date.now()}`;
        if (overlay) overlay.getContext('2d').clearRect(0,0,overlay.width,overlay.height);
      }
    });
  }

  // ===== EXPORT =====
  async function exportPdf() {
    try {
      const fileId = appState.fileId || document.body.dataset.fileId || localStorage.getItem("currentFileId");
      if (!fileId) {
        showToast("Please upload and process a document before downloading.", "error");
        return;
      }

      showLoading("Preparing optimized PDF...");

      // Settings format
      const settingsStr = getSettingsString();
      const settingsRaw = JSON.parse(decodeURIComponent(settingsStr));
      settingsRaw.export_quality = selExportQuality.value; // add the export quality

      const response = await fetch("/api/export", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          file_id: fileId,
          page_count: appState.pageCount,
          settings: settingsRaw
        })
      });

      const data = await safeJsonResponse(response);

      if (data.status !== "success") {
        throw new Error(data.message || "Export failed");
      }

      hideLoading();

      if (!data.download_url) {
        throw new Error("Export completed but download URL is missing.");
      }

      window.location.href = data.download_url;
    } catch (error) {
      hideLoading();
      showToast(error.message, "error");
    }
  }

  btnDownload.addEventListener("click", exportPdf);

  // ===== HELPERS =====
  function showLoading(msg) { loadingMsg.textContent = msg; loadingOverlay.classList.add('active'); }
  function hideLoading() { loadingOverlay.classList.remove('active'); }
});
