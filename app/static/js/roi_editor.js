let canvas, ctx;
let isDragging = false;
let startX, startY, endX, endY;
let roi = { x1: 0.0, y1: 0.0, x2: 1.0, y2: 1.0 };
let target = { x: 0.5, y: 0.3 };

document.addEventListener("DOMContentLoaded", () => {
    canvas = document.getElementById("roiCanvas");
    const wrapper = document.getElementById("previewWrapper");
    if (!canvas || !wrapper) return;

    ctx = canvas.getContext("2d");

    // Load initial values from dataset
    roi.x1 = parseFloat(wrapper.dataset.roiX1) || 0.0;
    roi.y1 = parseFloat(wrapper.dataset.roiY1) || 0.0;
    roi.x2 = parseFloat(wrapper.dataset.roiX2) || 1.0;
    roi.y2 = parseFloat(wrapper.dataset.roiY2) || 1.0;
    target.x = parseFloat(wrapper.dataset.targetX) || 0.5;
    target.y = parseFloat(wrapper.dataset.targetY) || 0.3;

    function resizeCanvas() {
        const img = document.getElementById("cameraStreamImg");
        if (!img || img.clientWidth === 0) return;
        canvas.width = img.clientWidth;
        canvas.height = img.clientHeight;
        draw();
    }

    window.addEventListener("resize", resizeCanvas);

    const img = document.getElementById("cameraStreamImg");
    if (img) {
        if (img.complete) {
            resizeCanvas();
        } else {
            img.onload = resizeCanvas;
            img.onerror = resizeCanvas;
        }
    }
    // Periodic check in case image renders dynamically
    setTimeout(resizeCanvas, 100);
    setTimeout(resizeCanvas, 500);

    canvas.addEventListener("mousedown", (e) => {
        const rect = canvas.getBoundingClientRect();
        startX = (e.clientX - rect.left) / canvas.width;
        startY = (e.clientY - rect.top) / canvas.height;
        isDragging = true;
    });

    canvas.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const rect = canvas.getBoundingClientRect();
        endX = (e.clientX - rect.left) / canvas.width;
        endY = (e.clientY - rect.top) / canvas.height;

        roi.x1 = Math.max(0.0, Math.min(startX, endX));
        roi.y1 = Math.max(0.0, Math.min(startY, endY));
        roi.x2 = Math.min(1.0, Math.max(startX, endX));
        roi.y2 = Math.min(1.0, Math.max(startY, endY));

        draw();
    });

    canvas.addEventListener("mouseup", () => {
        isDragging = false;
    });

    canvas.addEventListener("click", (e) => {
        if (isDragging) return;
        const rect = canvas.getBoundingClientRect();
        target.x = Math.max(0.0, Math.min(1.0, (e.clientX - rect.left) / canvas.width));
        target.y = Math.max(0.0, Math.min(1.0, (e.clientY - rect.top) / canvas.height));
        draw();
    });
});

function draw() {
    if (!ctx || !canvas) return;
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    // Draw ROI Rect (Green box)
    const rx = roi.x1 * w;
    const ry = roi.y1 * h;
    const rw = (roi.x2 - roi.x1) * w;
    const rh = (roi.y2 - roi.y1) * h;

    ctx.strokeStyle = "#10B981";
    ctx.lineWidth = 3;
    ctx.strokeRect(rx, ry, rw, rh);
    ctx.fillStyle = "rgba(16, 185, 129, 0.2)";
    ctx.fillRect(rx, ry, rw, rh);

    // Draw ROI Label
    ctx.fillStyle = "#10B981";
    ctx.font = "bold 14px sans-serif";
    ctx.fillText("Detection ROI", rx + 8, ry > 25 ? ry - 8 : ry + 20);

    // Draw Target Crosshair (Red cross)
    const tx = target.x * w;
    const ty = target.y * h;

    ctx.strokeStyle = "#EF4444";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(tx - 20, ty);
    ctx.lineTo(tx + 20, ty);
    ctx.moveTo(tx, ty - 20);
    ctx.lineTo(tx, ty + 20);
    ctx.stroke();

    ctx.fillStyle = "#EF4444";
    ctx.beginPath();
    ctx.arc(tx, ty, 5, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#EF4444";
    ctx.font = "bold 13px sans-serif";
    ctx.fillText(`Target (${Math.round(target.x * 100)}%, ${Math.round(target.y * 100)}%)`, tx + 10, ty - 10);
}

function saveROIAndTarget() {
    const presetId = document.getElementById("presetId").value;
    const baseNo = parseInt(document.getElementById("basePresetNo").value);
    const liveNo = parseInt(document.getElementById("livePresetNo").value);

    if (baseNo === liveNo) {
        alert("⚠️ BASE Preset 번호와 LIVE Preset 번호는 서로 다르게 지정해야 합니다!");
        return;
    }

    const payload = {
        base_preset_no: baseNo,
        live_preset_no: liveNo,
        target_mode: document.getElementById("targetMode").value,
        vertical_metric: document.getElementById("verticalMetric").value,
        person_count_policy: document.getElementById("personCountPolicy").value,
        expected_person_count: parseInt(document.getElementById("expectedCount").value) || null,
        minimum_person_count: parseInt(document.getElementById("minCount").value) || null,
        pan_limit: parseFloat(document.getElementById("panLimit").value),
        tilt_limit: parseFloat(document.getElementById("tiltLimit").value),
        roi_x1: roi.x1,
        roi_y1: roi.y1,
        roi_x2: roi.x2,
        roi_y2: roi.y2,
        target_x: target.x,
        target_y: target.y
    };

    fetch(`/api/presets/${presetId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
        .then(res => {
            if (!res.ok) return res.json().then(e => { throw new Error(e.detail); });
            return res.json();
        })
        .then(data => {
            alert("ROI 영역 및 Target 구도 설정이 정상적으로 저장되었습니다!");
        })
        .catch(err => {
            alert("저장 실패: " + err.message);
        });
}
