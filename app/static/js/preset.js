function openAddPresetModal() {
    document.getElementById("modalPresetTitle").innerText = "프리셋 신규 추가";
    document.getElementById("presetId").value = "";
    document.getElementById("presetForm").reset();
    document.getElementById("presetModal").style.display = "flex";
}

function openEditPresetModal(btn) {
    const ds = btn.dataset;
    document.getElementById("modalPresetTitle").innerText = `프리셋 수정 - ${ds.name}`;
    document.getElementById("presetId").value = ds.id;
    document.getElementById("presetName").value = ds.name;
    document.getElementById("basePresetNo").value = ds.base;
    document.getElementById("livePresetNo").value = ds.live;
    document.getElementById("presetTargetMode").value = ds.mode;
    document.getElementById("presetVerticalMetric").value = ds.vertical;
    document.getElementById("presetCountPolicy").value = ds.policy;
    document.getElementById("presetAutoEnabled").value = ds.enabled === "true" ? "true" : "false";

    document.getElementById("presetModal").style.display = "flex";
}

function closePresetModal() {
    document.getElementById("presetModal").style.display = "none";
}

function handlePresetSubmit(e) {
    e.preventDefault();

    const presetId = document.getElementById("presetId").value;
    const cameraId = parseInt(document.getElementById("cameraId").value);
    const baseNo = parseInt(document.getElementById("basePresetNo").value);
    const liveNo = parseInt(document.getElementById("livePresetNo").value);

    if (baseNo === liveNo) {
        alert("⚠️ BASE Preset 번호와 LIVE Preset 번호는 서로 다르게 지정해야 합니다!");
        return;
    }

    const payload = {
        camera_id: cameraId,
        name: document.getElementById("presetName").value,
        base_preset_no: baseNo,
        live_preset_no: liveNo,
        target_mode: document.getElementById("presetTargetMode").value,
        vertical_metric: document.getElementById("presetVerticalMetric").value,
        person_count_policy: document.getElementById("presetCountPolicy").value,
        auto_set_enabled: document.getElementById("presetAutoEnabled").value === "true"
    };

    const method = presetId ? "PUT" : "POST";
    const url = presetId ? `/api/presets/${presetId}` : "/api/presets";

    fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
        .then(res => {
            if (!res.ok) return res.json().then(err => { throw new Error(err.detail); });
            return res.json();
        })
        .then(data => {
            alert("프리셋 정보가 정상적으로 저장되었습니다!");
            closePresetModal();
            window.location.reload();
        })
        .catch(err => alert("저장 실패: " + err.message));
}

function deletePreset(presetId) {
    if (!confirm("정말로 이 프리셋을 삭제하시겠습니까?")) {
        return;
    }
    fetch(`/api/presets/${presetId}`, { method: "DELETE" })
        .then(res => {
            if (!res.ok) return res.json().then(e => { throw new Error(e.detail); });
            return res.json();
        })
        .then(data => {
            alert("프리셋이 삭제되었습니다.");
            window.location.reload();
        })
        .catch(err => alert("삭제 실패: " + err.message));
}
