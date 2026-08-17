/**
 * PTZ Auto Set Stream Deck Plugin Bridge
 * Stream Deck과 FastAPI Server간 REST 및 WebSocket 실시간 상태 동기화
 */

const SERVER_HOST = "http://localhost:8000";
const WS_HOST = "ws://localhost:8000/ws/status";

class StreamDeckPTZBridge {
    constructor() {
        this.ws = null;
        this.presetStatuses = {};
        this.connectWebSocket();
    }

    connectWebSocket() {
        this.ws = new WebSocket(WS_HOST);
        this.ws.onopen = () => console.log("[StreamDeckBridge] Connected to PTZ AutoSet Server");
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "preset_status") {
                const { preset_id, status } = data.payload;
                this.presetStatuses[preset_id] = status;
                this.updateKeyDisplay(preset_id, status);
            }
        };
        this.ws.onclose = () => setTimeout(() => this.connectWebSocket(), 3000);
    }

    triggerAutoSetAll() {
        fetch(`${SERVER_HOST}/api/autoset/all`, { method: "POST" });
    }

    triggerRetryFailed() {
        fetch(`${SERVER_HOST}/api/autoset/retry-failed`, { method: "POST" });
    }

    triggerPresetAutoSet(presetId) {
        fetch(`${SERVER_HOST}/api/autoset/presets/${presetId}`, { method: "POST" });
    }

    updateKeyDisplay(presetId, status) {
        // Stream Deck Key Color Rules
        // READY: Gray (#6B7280)
        // RUNNING: Yellow (#F59E0B)
        // SUCCESS: Green (#10B981)
        // FAILED: Red (#EF4444)
        console.log(`[StreamDeck] Preset #${presetId} updated -> ${status}`);
    }
}

window.ptzBridge = new StreamDeckPTZBridge();
