let draftTestPassed = false;

function openAddCameraModal() {
    document.getElementById("modalTitle").innerText = "카메라 신규 추가";
    document.getElementById("camId").value = "";
    document.getElementById("cameraForm").reset();
    document.getElementById("draftTestResult").style.display = "none";
    draftTestPassed = false;
    document.getElementById("cameraModal").style.display = "flex";
}

function openEditCameraModal(btn) {
    const ds = btn.dataset;
    document.getElementById("modalTitle").innerText = `카메라 수정 - ${ds.name}`;
    document.getElementById("camId").value = ds.id;
    document.getElementById("camName").value = ds.name;
    document.getElementById("camIp").value = ds.ip;
    document.getElementById("camPort").value = ds.port;
    document.getElementById("camProtocol").value = ds.protocol;
    document.getElementById("camEnabled").value = ds.enabled === "true" ? "true" : "false";
    document.getElementById("camRtspUrl").value = ds.rtspUrl;
    document.getElementById("camRtspUser").value = ds.rtspUser || "";
    document.getElementById("camRtspPass").value = "";

    document.getElementById("draftTestResult").style.display = "none";
    draftTestPassed = false;
    document.getElementById("cameraModal").style.display = "flex";
}

function closeCameraModal() {
    document.getElementById("cameraModal").style.display = "none";
}

function runDraftTest() {
    const box = document.getElementById("draftTestResult");
    box.style.display = "block";
    document.getElementById("draftViscaStatus").innerText = "🟡 TESTING...";
    document.getElementById("draftRtspStatus").innerText = "🟡 TESTING...";
    document.getElementById("draftTestError").innerText = "";

    const payload = {
        ip_address: document.getElementById("camIp").value,
        visca_port: parseInt(document.getElementById("camPort").value),
        visca_protocol: document.getElementById("camProtocol").value,
        rtsp_url: document.getElementById("camRtspUrl").value,
        rtsp_username: document.getElementById("camRtspUser").value || null,
        rtsp_password: document.getElementById("camRtspPass").value || null
    };

    fetch("/api/cameras/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
        .then(res => {
            if (!res.ok) return res.json().then(e => { throw new Error(e.detail); });
            return res.json();
        })
        .then(data => {
            draftTestPassed = data.success;
            document.getElementById("draftViscaStatus").innerText = data.visca.status === "CONNECTED" ? `🟢 CONNECTED (${data.visca.latency_ms}ms)` : `🔴 ${data.visca.status}`;
            document.getElementById("draftRtspStatus").innerText = data.rtsp.status === "CONNECTED" ? `🟢 STREAMING (${data.rtsp.resolution})` : `🔴 ${data.rtsp.status}`;

            if (!data.success) {
                const errs = [data.visca.error, data.rtsp.error].filter(Boolean).join(" | ");
                document.getElementById("draftTestError").innerText = "⚠️ 경고: " + errs;
            }
        })
        .catch(err => {
            draftTestPassed = false;
            document.getElementById("draftTestError").innerText = "❌ 테스트 실패: " + err.message;
        });
}

function handleCameraSubmit(e) {
    e.preventDefault();

    if (!draftTestPassed) {
        if (!confirm("⚠️ 현재 장비 연결 테스트에 실패했거나 실행하지 않았습니다. 그래도 저장을 진행하시겠습니까?")) {
            return;
        }
    }

    const camId = document.getElementById("camId").value;
    const payload = {
        name: document.getElementById("camName").value,
        ip_address: document.getElementById("camIp").value,
        visca_port: parseInt(document.getElementById("camPort").value),
        visca_protocol: document.getElementById("camProtocol").value,
        enabled: document.getElementById("camEnabled").value === "true",
        rtsp_url: document.getElementById("camRtspUrl").value,
        rtsp_username: document.getElementById("camRtspUser").value || null
    };

    const pass = document.getElementById("camRtspPass").value;
    if (pass) payload.rtsp_password = pass;

    const method = camId ? "PUT" : "POST";
    const url = camId ? `/api/cameras/${camId}` : "/api/cameras";

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
            alert("카메라 설정이 저장되었습니다!");
            closeCameraModal();
            window.location.reload();
        })
        .catch(err => alert("❌ 저장 실패: " + err.message));
}

function testExistingCamera(camId) {
    const vBadge = document.getElementById(`viscaStatus-${camId}`);
    const rBadge = document.getElementById(`rtspStatus-${camId}`);
    if (vBadge) vBadge.innerText = "TESTING...";
    if (rBadge) rBadge.innerText = "TESTING...";

    fetch(`/api/cameras/${camId}/test-connection`, { method: "POST" })
        .then(res => res.json())
        .then(data => console.log("Re-test result:", data))
        .catch(err => alert("테스트 실패: " + err));
}

function deleteCamera(camId) {
    if (!confirm("정말로 이 카메라를 삭제하시겠습니까? (등록된 프리셋이 있을 경우 삭제가 차단됩니다)")) {
        return;
    }
    fetch(`/api/cameras/${camId}`, { method: "DELETE" })
        .then(res => {
            if (!res.ok) return res.json().then(e => { throw new Error(e.detail); });
            return res.json();
        })
        .then(data => {
            alert("카메라가 삭제되었습니다.");
            window.location.reload();
        })
        .catch(err => alert("❌ 삭제 차단: " + err.message));
}

// WebSocket 런타임 상태 브로드캐스트 이벤트 수신
if (window.statusWS) {
    const origHandler = window.statusWS.handleEvent.bind(window.statusWS);
    window.statusWS.handleEvent = function (msg) {
        origHandler(msg);
        if (msg.type === "camera_health_update") {
            const { camera_id, visca_status, rtsp_status, visca_latency_ms, rtsp_resolution } = msg.payload;
            const vBadge = document.getElementById(`viscaStatus-${camera_id}`);
            const rBadge = document.getElementById(`rtspStatus-${camera_id}`);
            const vLat = document.getElementById(`viscaLatency-${camera_id}`);
            const rRes = document.getElementById(`rtspRes-${camera_id}`);

            if (vBadge) {
                vBadge.innerText = visca_status;
                vBadge.className = `health-badge status-${visca_status.toLowerCase()}`;
            }
            if (rBadge) {
                rBadge.innerText = rtsp_status;
                rBadge.className = `health-badge status-${rtsp_status.toLowerCase()}`;
            }
            if (vLat) vLat.innerText = visca_latency_ms ? `${visca_latency_ms}ms` : "-";
            if (rRes) rRes.innerText = rtsp_resolution || "-";
        }
    };
}
