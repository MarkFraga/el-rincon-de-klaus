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

/* ===== GENERATE PODCAST ===== */
async function generatePodcast() {
    var topic = document.getElementById('topic-input').value.trim();
    if (!topic) {
        shakeElement(document.getElementById('topic-input'));
        return;
    }

    var btn = document.getElementById('btn-generate');
    btn.disabled = true;
    btn.textContent = 'Iniciando...';

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
        showScreen('progress');
        resetAgentCards();
        connectWebSocket(data.job_id);
        startPolling(data.job_id);
    } catch (err) {
        alert('No se pudo iniciar la generacion: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">&#9889;</span> GENERAR PODCAST';
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

        var expertText = '';
        if (data.expert_name && data.country) {
            expertText = 'Con ' + data.expert_name + ' desde ' + data.country;
        } else if (data.expert_name) {
            expertText = 'Con ' + data.expert_name;
        }
        document.getElementById('player-expert').textContent = expertText;

        showScreen('player');
        var audioUrl = data.audio_url || '/api/audio/' + state.jobId;
        loadAudio(audioUrl);
        loadPodcastList();
        return;
    }

    if (data.status === 'error') {
        stopPolling();
        closeWebSocket();
        alert('Error: ' + (data.error || 'Error desconocido'));
        showScreen('home');
        return;
    }

    // Update agent cards
    if (data.agent) {
        updateAgentCard(data.agent, data.agent_status || data.status, data.message || '');
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

/* ===== AGENT CARDS ===== */
var agentMap = {
    'web': 'web',
    'academic': 'academic',
    'deep': 'deep',
    'organizer': 'organizer'
};

function resetAgentCards() {
    Object.keys(agentMap).forEach(function(key) {
        var card = document.getElementById('agent-' + key);
        var dot = document.getElementById('dot-' + key);
        var activity = document.getElementById('activity-' + key);
        if (card) card.className = 'agent-card';
        if (dot) dot.className = 'status-dot pending';
        if (activity) activity.textContent = 'En espera';
    });
    updateProgressBar(0);
    document.getElementById('audio-gen-text').textContent = 'Esperando generacion de audio...';
}

function updateAgentCard(agentName, status, message) {
    var key = agentMap[agentName] || agentName;
    var card = document.getElementById('agent-' + key);
    var dot = document.getElementById('dot-' + key);
    var activity = document.getElementById('activity-' + key);

    if (!card) return;

    // Update card class
    card.className = 'agent-card';
    if (status === 'running') card.classList.add('running');
    else if (status === 'done' || status === 'complete') card.classList.add('done');

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
            html += '<div class="podcast-item" onclick="playPodcast(\'' +
                escapeAttr(p.id || p.job_id) + '\', \'' +
                escapeAttr(p.topic) + '\', \'' +
                escapeAttr(p.expert_name || '') + '\', \'' +
                escapeAttr(p.country || '') + '\')">' +
                '<div class="podcast-item-icon">&#127911;</div>' +
                '<div class="podcast-item-info">' +
                '<div class="podcast-item-title">' + escapeHtml(p.topic) + '</div>' +
                '<div class="podcast-item-meta">' + date + '</div>' +
                '</div>' +
                '<div class="podcast-item-play">&#9654;</div>' +
                '</div>';
        });
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = '<div class="empty-state">No se pudieron cargar los podcasts</div>';
    }
}

function playPodcast(id, topic, expertName, country) {
    document.getElementById('player-topic').textContent = topic;
    var expertText = '';
    if (expertName && country) {
        expertText = 'Con ' + expertName + ' desde ' + country;
    } else if (expertName) {
        expertText = 'Con ' + expertName;
    }
    document.getElementById('player-expert').textContent = expertText;
    showScreen('player');
    loadAudio('/api/audio/' + id);
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
});
