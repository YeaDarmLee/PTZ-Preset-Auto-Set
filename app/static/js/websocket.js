class StatusWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectDelay = 2000;
        self = this;
        this.connect();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/status`;
        
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log("[StatusWebSocket] Connected to server.");
            const indicator = document.querySelector(".status-indicator");
            if (indicator) indicator.className = "status-indicator ready";
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                this.handleEvent(msg);
            } catch (e) {
                console.error("[StatusWebSocket] Parse error:", e);
            }
        };

        this.ws.onclose = () => {
            console.warn("[StatusWebSocket] Disconnected. Reconnecting...");
            const indicator = document.querySelector(".status-indicator");
            if (indicator) indicator.className = "status-indicator disconnected";
            setTimeout(() => this.connect(), this.reconnectDelay);
        };
    }

    handleEvent(msg) {
        if (msg.type === "preset_status") {
            const { camera_id, preset_id, status } = msg.payload;
            const item = document.getElementById(`presetItem-${preset_id}`);
            if (item) {
                item.className = `preset-item status-${status.toLowerCase()}`;
            }
            if (window.updateSummaryCounters) window.updateSummaryCounters();
        } else if (msg.type === "system_reset") {
            document.querySelectorAll(".preset-item").forEach(el => {
                el.className = "preset-item status-ready";
            });
            if (window.updateSummaryCounters) window.updateSummaryCounters();
        }
    }
}

window.statusWS = new StatusWebSocket();
