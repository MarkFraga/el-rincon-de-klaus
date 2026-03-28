/* ===== AUDIO PLAYER ===== */
var audio = new Audio();
var currentSpeed = 1;
var isSeeking = false;
var previousVolume = 1;

/* ===== LOAD AUDIO ===== */
function loadAudio(url) {
    audio.pause();
    audio.src = url;
    audio.playbackRate = currentSpeed;
    audio.load();

    updatePlayButton(false);
    document.getElementById('seek-played').style.width = '0%';
    document.getElementById('seek-handle').style.left = '0%';
    document.getElementById('time-current').textContent = '0:00';
    document.getElementById('time-total').textContent = '0:00';

    var bufferedEl = document.getElementById('seek-buffered');
    if (bufferedEl) bufferedEl.style.width = '0%';

    audio.onloadedmetadata = function() {
        document.getElementById('time-total').textContent = formatTime(audio.duration);
    };

    audio.ontimeupdate = function() {
        if (isSeeking) return;
        if (!audio.duration) return;
        var pct = (audio.currentTime / audio.duration) * 100;
        document.getElementById('seek-played').style.width = pct + '%';
        document.getElementById('seek-handle').style.left = pct + '%';
        document.getElementById('time-current').textContent = formatTime(audio.currentTime);
    };

    audio.onprogress = function() {
        updateBuffered();
    };

    audio.onended = function() {
        updatePlayButton(false);
    };

    audio.onerror = function() {
        document.getElementById('time-total').textContent = '--:--';
    };
}

/* ===== BUFFERED PROGRESS ===== */
function updateBuffered() {
    var bufferedEl = document.getElementById('seek-buffered');
    if (!bufferedEl || !audio.duration) return;

    if (audio.buffered.length > 0) {
        var bufferedEnd = audio.buffered.end(audio.buffered.length - 1);
        var pct = (bufferedEnd / audio.duration) * 100;
        bufferedEl.style.width = pct + '%';
    }
}

/* ===== PLAY / PAUSE ===== */
function togglePlay() {
    if (!audio.src) return;
    if (audio.paused) {
        audio.play().then(function() {
            updatePlayButton(true);
        }).catch(function() {
            // Autoplay blocked
        });
    } else {
        audio.pause();
        updatePlayButton(false);
    }
}

function pauseAudio() {
    audio.pause();
    updatePlayButton(false);
}

function updatePlayButton(isPlaying) {
    var iconPlay = document.getElementById('icon-play');
    var iconPause = document.getElementById('icon-pause');
    if (isPlaying) {
        iconPlay.style.display = 'none';
        iconPause.style.display = 'block';
    } else {
        iconPlay.style.display = 'block';
        iconPause.style.display = 'none';
    }
}

/* ===== SEEK ===== */
function seek(e) {
    if (!audio.duration) return;
    var bar = document.getElementById('seek-bar');
    var rect = bar.getBoundingClientRect();
    var x = e.clientX !== undefined ? e.clientX : (e.touches ? e.touches[0].clientX : 0);
    var pct = Math.min(1, Math.max(0, (x - rect.left) / rect.width));
    audio.currentTime = pct * audio.duration;

    document.getElementById('seek-played').style.width = (pct * 100) + '%';
    document.getElementById('seek-handle').style.left = (pct * 100) + '%';
    document.getElementById('time-current').textContent = formatTime(audio.currentTime);
}

/* Touch-based seeking */
(function() {
    document.addEventListener('DOMContentLoaded', function() {
        var seekBar = document.getElementById('seek-bar');
        if (!seekBar) return;

        seekBar.addEventListener('touchstart', function(e) {
            isSeeking = true;
            handleSeekTouch(e);
        }, { passive: false });

        seekBar.addEventListener('touchmove', function(e) {
            e.preventDefault();
            handleSeekTouch(e);
        }, { passive: false });

        seekBar.addEventListener('touchend', function() {
            isSeeking = false;
        });

        function handleSeekTouch(e) {
            if (!audio.duration) return;
            var rect = seekBar.getBoundingClientRect();
            var x = e.touches[0].clientX;
            var pct = Math.min(1, Math.max(0, (x - rect.left) / rect.width));
            audio.currentTime = pct * audio.duration;
            document.getElementById('seek-played').style.width = (pct * 100) + '%';
            document.getElementById('seek-handle').style.left = (pct * 100) + '%';
            document.getElementById('time-current').textContent = formatTime(audio.currentTime);
        }
    });
})();

/* ===== VOLUME CONTROL ===== */
function toggleMute() {
    if (audio.volume > 0) {
        previousVolume = audio.volume;
        audio.volume = 0;
    } else {
        audio.volume = previousVolume || 1;
    }
    updateVolumeUI();
}

function updateVolumeUI() {
    var fill = document.getElementById('volume-fill');
    var icon = document.getElementById('volume-icon');
    if (!fill || !icon) return;

    var vol = audio.volume;
    fill.style.width = (vol * 100) + '%';

    if (vol === 0) {
        icon.innerHTML = '&#128263;'; // muted speaker
    } else if (vol < 0.5) {
        icon.innerHTML = '&#128264;'; // low volume
    } else {
        icon.innerHTML = '&#128266;'; // high volume
    }
}

(function() {
    document.addEventListener('DOMContentLoaded', function() {
        var volumeBar = document.getElementById('volume-bar');
        if (!volumeBar) return;

        volumeBar.addEventListener('click', function(e) {
            var rect = volumeBar.getBoundingClientRect();
            var pct = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
            audio.volume = pct;
            updateVolumeUI();
        });

        volumeBar.addEventListener('touchstart', function(e) {
            handleVolumeTouch(e);
        }, { passive: false });

        volumeBar.addEventListener('touchmove', function(e) {
            e.preventDefault();
            handleVolumeTouch(e);
        }, { passive: false });

        function handleVolumeTouch(e) {
            var rect = volumeBar.getBoundingClientRect();
            var x = e.touches[0].clientX;
            var pct = Math.min(1, Math.max(0, (x - rect.left) / rect.width));
            audio.volume = pct;
            updateVolumeUI();
        }
    });
})();

/* ===== SPEED ===== */
function setSpeed(speed) {
    currentSpeed = speed;
    audio.playbackRate = speed;
    document.querySelectorAll('.speed-btn').forEach(function(b) {
        b.classList.remove('active');
    });
    var active = document.querySelector('[data-speed="' + speed + '"]');
    if (active) active.classList.add('active');
}

/* ===== FORMAT TIME ===== */
function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return m + ':' + (s < 10 ? '0' : '') + s;
}

/* ===== DOWNLOAD ===== */
function downloadAudio() {
    if (!audio.src) return;
    var a = document.createElement('a');
    a.href = audio.src;
    a.download = 'el-rincon-de-klaus.mp3';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}
