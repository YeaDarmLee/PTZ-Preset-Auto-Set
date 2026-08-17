function triggerAutoSetAll() {
    fetch('/api/autoset/all', { method: 'POST' })
        .then(res => res.json())
        .then(data => console.log('AutoSet All:', data))
        .catch(err => console.error(err));
}

function triggerRetryFailed() {
    fetch('/api/autoset/retry-failed', { method: 'POST' })
        .then(res => res.json())
        .then(data => console.log('Retry Failed:', data))
        .catch(err => console.error(err));
}

function resetUIStatus() {
    fetch('/api/autoset/reset-status', { method: 'POST' })
        .then(res => res.json())
        .then(data => console.log('Reset UI:', data))
        .catch(err => console.error(err));
}

function triggerCancel() {
    fetch('/api/autoset/cancel', { method: 'POST' })
        .then(res => res.json())
        .then(data => console.log('Cancel:', data))
        .catch(err => console.error(err));
}

function triggerSinglePreset(presetId) {
    fetch(`/api/autoset/presets/${presetId}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => console.log(`Single Preset #${presetId}:`, data))
        .catch(err => console.error(err));
}

window.updateSummaryCounters = function() {
    const successItems = document.querySelectorAll('.preset-item.status-success').length;
    const failedItems = document.querySelectorAll('.preset-item.status-failed').length;

    const sEl = document.getElementById('successCount');
    const fEl = document.getElementById('failedCount');

    if (sEl) sEl.innerText = successItems;
    if (fEl) fEl.innerText = failedItems;
};

document.addEventListener("DOMContentLoaded", () => {
    window.updateSummaryCounters();
});
