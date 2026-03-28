/* ===== STATE ===== */
const state = {
    screen: 'home',
    jobId: null,
    ws: null,
    pollTimer: null
};

/* ===== SCREEN NAVIGATION ===== */
function showScreen(name) {
    document.querySelectorAll('.screen').forEach(function(s) {
        s.style.display = 'none';
    });
    var el = document.getElementById('screen-' + name);
    if (el) {
        el.style.display = 'flex';
        // Re-trigger animation
        el.style.animation = 'none';
        el.offsetHeight; // reflow
        el.style.animation = '';
    }
    state.screen = name;
}

/* ===== TOAST NOTIFICATIONS ===== */
function showToast(message, type) {
    type = type || 'error';
    var container = document.getElementById('toast-container');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'toast' + (type === 'success' ? ' toast-success' : '');

    var icon = type === 'success' ? '&#10003;' : '&#9888;';
    toast.innerHTML = '<span class="toast-icon">' + icon + '</span><span>' + escapeHtml(message) + '</span>';
    container.appendChild(toast);

    setTimeout(function() {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 4000);
}

/* ===== FRIENDLY ERROR MESSAGES ===== */
function friendlyError(err) {
    var msg = (err && err.message) ? err.message : String(err);

    if (msg.indexOf('Failed to fetch') !== -1 || msg.indexOf('NetworkError') !== -1) {
        return 'No se pudo conectar con el servidor. Verifica tu conexion a internet.';
    }
    if (msg.indexOf('500') !== -1) {
        return 'Error interno del servidor. Intenta de nuevo en unos momentos.';
    }
    if (msg.indexOf('429') !== -1) {
        return 'Demasiadas solicitudes. Espera un momento antes de intentar de nuevo.';
    }
    if (msg.indexOf('404') !== -1) {
        return 'Servicio no encontrado. Verifica que el servidor este activo.';
    }
    if (msg.indexOf('timeout') !== -1 || msg.indexOf('Timeout') !== -1) {
        return 'La solicitud tomo demasiado tiempo. Intenta de nuevo.';
    }
    return 'Ocurrio un error inesperado. Intenta de nuevo.';
}

/* ===== GENERATE PODCAST ===== */
async function generatePodcast() {
    var topic = document.getElementById('topic-input').value.trim();
    if (!topic) {
        shakeElement(document.getElementById('topic-input'));
        return;
    }

    var btn = document.getElementById('btn-generate');
    var btnText = btn.querySelector('.btn-text');
    var btnIcon = btn.querySelector('.btn-icon');
    var btnSpinner = btn.querySelector('.btn-spinner');

    // Set generating state
    btn.disabled = true;
    if (btnText) btnText.textContent = 'GENERANDO...';
    if (btnIcon) btnIcon.style.display = 'none';
    if (btnSpinner) btnSpinner.style.display = 'inline-block';

    try {
        var res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic: topic })
        });

        if (!res.ok) {
            throw new Error('Error del servidor: ' + res.status);
        }

        var data = await res.json();
        state.jobId = data.job_id;

        document.getElementById('progress-topic').textContent = topic;
        // Hide guest info until we get it
        var guestInfoEl = document.getElementById('progress-guest-info');
        if (guestInfoEl) guestInfoEl.style.display = 'none';

        showScreen('progress');
        resetAgentCards();
        connectWebSocket(data.job_id);
        startPolling(data.job_id);
    } catch (err) {
        showToast(friendlyError(err));
    } finally {
        // Reset button state
        btn.disabled = false;
        if (btnText) btnText.textContent = 'GENERAR PODCAST';
        if (btnIcon) btnIcon.style.display = '';
        if (btnSpinner) btnSpinner.style.display = 'none';
    }
}

/* ===== WEBSOCKET ===== */
function connectWebSocket(jobId) {
    if (state.ws) {
        state.ws.onclose = null;
        state.ws.close();
    }

    var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = protocol + '//' + location.host + '/ws/progress/' + jobId;

    try {
        state.ws = new WebSocket(url);
    } catch (e) {
        return;
    }

    state.ws.onmessage = function(e) {
        try {
            var data = JSON.parse(e.data);
            handleProgress(data);
        } catch (err) {
            // ignore malformed messages
        }
    };

    state.ws.onclose = function() {
        if (state.screen === 'progress') {
            setTimeout(function() {
                connectWebSocket(jobId);
            }, 2000);
        }
    };

    state.ws.onerror = function() {
        // Will trigger onclose, which handles reconnect
    };
}

/* ===== PROGRESS HANDLING ===== */
function handleProgress(data) {
    if (data.status === 'complete') {
        stopPolling();
        closeWebSocket();

        // Set player info
        document.getElementById('player-topic').textContent =
            document.getElementById('progress-topic').textContent;

        var guestText = '';
        if (data.guest_name && data.guest_role && data.guest_country) {
            guestText = 'Con ' + data.guest_name + ' (' + data.guest_role + ') desde ' + data.guest_country;
        } else if (data.guest_name && data.guest_country) {
            guestText = 'Con ' + data.guest_name + ' desde ' + data.guest_country;
        } else if (data.guest_name) {
            guestText = 'Con ' + data.guest_name;
        }
        document.getElementById('player-expert').textContent = guestText;

        showScreen('player');
        var audioUrl = data.audio_url || '/api/audio/' + state.jobId;
        loadAudio(audioUrl);
        loadPodcastList();
        return;
    }

    if (data.status === 'error') {
        stopPolling();
        closeWebSocket();
        showToast(data.error ? friendlyError({ message: data.error }) : 'Ocurrio un error durante la generacion.');
        showScreen('home');
        return;
    }

    // Update agent cards
    if (data.agent) {
        updateAgentCard(data.agent, data.agent_status || data.status, data.message || '');
    }

    // Show guest info on progress screen as soon as available
    if (data.guest_name) {
        showProgressGuestInfo(data.guest_name, data.guest_role, data.guest_country);
    }

    // Update progress bar
    if (typeof data.progress === 'number') {
        updateProgressBar(data.progress);
    }

    // Update audio generation text
    if (data.audio_status) {
        document.getElementById('audio-gen-text').textContent = data.audio_status;
    }
}

/* ===== SHOW GUEST INFO ON PROGRESS SCREEN ===== */
function showProgressGuestInfo(name, role, country) {
    var infoEl = document.getElementById('progress-guest-info');
    var textEl = document.getElementById('progress-guest-text');
    if (!infoEl || !textEl) return;

    var parts = [];
    if (name) parts.push(name);
    if (role) parts.push(role);
    if (country) parts.push(country);

    if (parts.length > 0) {
        textEl.textContent = parts.join(' - ');
        infoEl.style.display = '';
    }
}

/* ===== AGENT CARDS ===== */
// Map backend agent names to frontend element suffixes
var agentMap = {
    'web': 'web',
    'web_search': 'web',
    'academic': 'academic',
    'deep': 'deep',
    'deep_research': 'deep',
    'organizer': 'organizer'
};

function resetAgentCards() {
    ['web', 'academic', 'deep', 'organizer'].forEach(function(key) {
        var card = document.getElementById('agent-' + key);
        var dot = document.getElementById('dot-' + key);
        var activity = document.getElementById('activity-' + key);
        if (card) {
            card.className = 'agent-card';
        }
        if (dot) dot.className = 'status-dot pending';
        if (activity) activity.textContent = 'En espera';
    });
    updateProgressBar(0);
    document.getElementById('audio-gen-text').textContent = 'Esperando generacion de audio...';
}

function updateAgentCard(agentName, status, message) {
    var key = agentMap[agentName];
    if (!key) key = agentName;

    var card = document.getElementById('agent-' + key);
    var dot = document.getElementById('dot-' + key);
    var activity = document.getElementById('activity-' + key);

    if (!card) return;

    // Update card class
    card.className = 'agent-card';
    if (status === 'running') {
        card.classList.add('running');
    } else if (status === 'done' || status === 'complete') {
        card.classList.add('done');
        // Flash green briefly
        card.classList.add('done-flash');
        setTimeout(function() {
            card.classList.remove('done-flash');
        }, 1500);
    }

    // Update dot
    if (dot) {
        dot.className = 'status-dot';
        if (status === 'running') dot.classList.add('running');
        else if (status === 'done' || status === 'complete') dot.classList.add('done');
        else if (status === 'error') dot.classList.add('error');
        else dot.classList.add('pending');
    }

    // Update activity text
    if (activity && message) {
        activity.textContent = message;
    }
}

function updateProgressBar(percent) {
    var pct = Math.min(100, Math.max(0, percent));
    document.getElementById('progress-bar').style.width = pct + '%';
    document.getElementById('progress-percent').textContent = Math.round(pct) + '%';
}

/* ===== POLLING FALLBACK ===== */
function startPolling(jobId) {
    stopPolling();
    state.pollTimer = setInterval(async function() {
        try {
            var res = await fetch('/api/status/' + jobId);
            if (!res.ok) return;
            var data = await res.json();
            handleProgress(data);
        } catch (e) {
            // Silently ignore polling errors
        }
    }, 5000);
}

function stopPolling() {
    if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}

function closeWebSocket() {
    if (state.ws) {
        state.ws.onclose = null;
        state.ws.close();
        state.ws = null;
    }
}

/* ===== CANCEL ===== */
async function cancelGeneration() {
    stopPolling();
    closeWebSocket();

    if (state.jobId) {
        try {
            await fetch('/api/cancel/' + state.jobId, { method: 'POST' });
        } catch (e) {
            // ignore
        }
    }

    state.jobId = null;
    showScreen('home');
}

/* ===== PODCAST LIST ===== */
async function loadPodcastList() {
    var container = document.getElementById('podcast-list');
    try {
        var res = await fetch('/api/podcasts');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        var podcasts = await res.json();

        if (!podcasts || podcasts.length === 0) {
            container.innerHTML = '<div class="empty-state">Aun no hay podcasts. Genera el primero!</div>';
            return;
        }

        var html = '';
        podcasts.forEach(function(p) {
            var date = p.created_at ? formatDate(p.created_at) : '';
            var guestName = p.guest_name || '';
            var guestRole = p.guest_role || '';
            var guestCountry = p.guest_country || '';

            // Build role line
            var roleLine = '';
            if (guestName && guestRole) {
                roleLine = guestName + ' - ' + guestRole;
            } else if (guestName) {
                roleLine = guestName;
            }

            // Build meta line with date and country
            var metaParts = [];
            if (date) metaParts.push(date);
            if (guestCountry) metaParts.push(guestCountry);

            var metaHtml = '';
            for (var i = 0; i < metaParts.length; i++) {
                if (i > 0) metaHtml += '<span class="podcast-item-meta-dot"></span>';
                metaHtml += escapeHtml(metaParts[i]);
            }

            html += '<div class="podcast-item" onclick="playPodcast(\'' +
                escapeAttr(p.id || p.job_id) + '\', \'' +
                escapeAttr(p.topic) + '\', \'' +
                escapeAttr(guestName) + '\', \'' +
                escapeAttr(guestCountry) + '\', \'' +
                escapeAttr(guestRole) + '\')">' +
                '<div class="podcast-item-icon">&#127911;</div>' +
                '<div class="podcast-item-info">' +
                '<div class="podcast-item-title">' + escapeHtml(p.topic) + '</div>' +
                (roleLine ? '<div class="podcast-item-role">' + escapeHtml(roleLine) + '</div>' : '') +
                '<div class="podcast-item-meta">' + metaHtml + '</div>' +
                '</div>' +
                '<div class="podcast-item-play">&#9654;</div>' +
                '</div>';
        });
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = '<div class="empty-state">No se pudieron cargar los podcasts</div>';
    }
}

function playPodcast(id, topic, guestName, guestCountry, guestRole) {
    state.jobId = id;
    document.getElementById('player-topic').textContent = topic;
    var guestText = '';
    if (guestName && guestRole && guestCountry) {
        guestText = 'Con ' + guestName + ' (' + guestRole + ') desde ' + guestCountry;
    } else if (guestName && guestCountry) {
        guestText = 'Con ' + guestName + ' desde ' + guestCountry;
    } else if (guestName) {
        guestText = 'Con ' + guestName;
    }
    document.getElementById('player-expert').textContent = guestText;
    showScreen('player');
    loadAudio('/api/audio/' + id);
}

/* ===== SHARE PODCAST ===== */
function sharePodcast() {
    var topic = document.getElementById('player-topic').textContent;
    var url = window.location.origin + '/api/audio/' + state.jobId;

    // Try native share API first (mobile)
    if (navigator.share) {
        navigator.share({
            title: 'El Rincon de Klaus: ' + topic,
            text: 'Escucha este podcast sobre ' + topic,
            url: url
        }).catch(function() {
            copyToClipboard(url);
        });
    } else {
        copyToClipboard(url);
    }
}

function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() {
            showShareToast();
        }).catch(function() {
            fallbackCopy(text);
        });
    } else {
        fallbackCopy(text);
    }
}

function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try {
        document.execCommand('copy');
        showShareToast();
    } catch (e) {
        showToast('No se pudo copiar el enlace', 'error');
    }
    document.body.removeChild(ta);
}

function showShareToast() {
    var toast = document.getElementById('share-toast');
    if (!toast) return;
    toast.style.display = 'block';
    toast.style.animation = 'none';
    toast.offsetHeight;
    toast.style.animation = 'toastIn 0.3s ease';
    setTimeout(function() {
        toast.style.display = 'none';
    }, 2500);
}

/* ===== GO HOME ===== */
function goHome() {
    if (typeof pauseAudio === 'function') pauseAudio();
    document.getElementById('topic-input').value = '';
    showScreen('home');
    loadPodcastList();
}

/* ===== UTILITIES ===== */
function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

function escapeAttr(text) {
    return (text || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function formatDate(isoStr) {
    try {
        var d = new Date(isoStr);
        return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch (e) {
        return '';
    }
}

function shakeElement(el) {
    el.style.animation = 'none';
    el.offsetHeight;
    el.style.animation = 'shake 0.4s ease';
    setTimeout(function() { el.style.animation = ''; }, 400);
}

// Add shake keyframe dynamically
(function() {
    var style = document.createElement('style');
    style.textContent = '@keyframes shake { 0%,100%{transform:translateX(0)} 20%{transform:translateX(-8px)} 40%{transform:translateX(8px)} 60%{transform:translateX(-4px)} 80%{transform:translateX(4px)} }';
    document.head.appendChild(style);
})();

/* ===== INIT ===== */
document.addEventListener('DOMContentLoaded', function() {
    showScreen('home');
    loadPodcastList();

    // Register service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(function(err) {
            console.log('SW registration failed:', err);
        });
    }

    // Enter key to generate
    document.getElementById('topic-input').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            generatePodcast();
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Skip if typing in an input field
        var tag = e.target.tagName.toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;

        if (e.code === 'Space' && state.screen === 'player') {
            e.preventDefault();
            togglePlay();
        }

        // Arrow keys for seeking and volume on player screen
        if (state.screen === 'player' && typeof audio !== 'undefined' && audio.duration) {
            if (e.code === 'ArrowLeft') {
                e.preventDefault();
                audio.currentTime = Math.max(0, audio.currentTime - 10);
            }
            if (e.code === 'ArrowRight') {
                e.preventDefault();
                audio.currentTime = Math.min(audio.duration, audio.currentTime + 10);
            }
            if (e.code === 'ArrowUp') {
                e.preventDefault();
                audio.volume = Math.min(1, audio.volume + 0.1);
                if (typeof updateVolumeUI === 'function') updateVolumeUI();
            }
            if (e.code === 'ArrowDown') {
                e.preventDefault();
                audio.volume = Math.max(0, audio.volume - 0.1);
                if (typeof updateVolumeUI === 'function') updateVolumeUI();
            }
        }
    });
});
