// =====================================================
// JARVIS Robot Face — Animation Engine + WebSocket
// =====================================================

// ---- State Definitions (iris color, glow, eyelid, pupil position) ----
const FACE_STATES = {
  idle: {
    irisVar:  '--iris-idle',    glowVar: '--glow-idle',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.0,
    lookX: 0, lookY: 0,
    label: 'STANDBY', badge: ''
  },
  listening: {
    irisVar:  '--iris-listen',  glowVar: '--glow-listen',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 0.85,
    lookX: 0, lookY: -6,
    label: 'LISTENING', badge: ''
  },
  thinking: {
    irisVar:  '--iris-think',   glowVar: '--glow-think',
    eyelidTop: 22, eyelidBot: 0, pupilScale: 0.75,
    lookX: -18, lookY: -18,
    label: 'THINKING', badge: ''
  },
  speaking: {
    irisVar:  '--iris-speak',   glowVar: '--glow-speak',
    eyelidTop: 5,  eyelidBot: 0, pupilScale: 1.1,
    lookX: 0, lookY: 0,
    label: 'SPEAKING', badge: ''
  },
  happy: {
    irisVar:  '--iris-happy',   glowVar: '--glow-happy',
    eyelidTop: 35, eyelidBot: 32, pupilScale: 1.2,
    lookX: 0, lookY: 5,
    label: 'HAPPY', badge: ''
  },
  concerned: {
    irisVar:  '--iris-concerned', glowVar: '--glow-concerned',
    eyelidTop: 18, eyelidBot: 0, pupilScale: 0.85,
    lookX: 0, lookY: 12,
    label: 'CONCERNED', badge: ''
  },
  sad: {
    irisVar:  '--iris-sad',     glowVar: '--glow-idle',
    eyelidTop: 28, eyelidBot: 0, pupilScale: 0.9,
    lookX: -10, lookY: 14,
    label: 'SAD', badge: ''
  },
  surprised: {
    irisVar:  '--iris-happy',   glowVar: '--glow-happy',
    eyelidTop: 0,  eyelidBot: 0, pupilScale: 1.3,
    lookX: 0, lookY: -4,
    label: 'SURPRISED', badge: ''
  },
  neutral: {
    irisVar:  '--iris-idle',    glowVar: '--glow-idle',
    eyelidTop: 0,  eyelidBot: 0, pupilScale: 1.0,
    lookX: 0, lookY: 0,
    label: 'STANDBY', badge: ''
  },
  sleepy: {
    irisVar:  '--iris-sleepy',  glowVar: '--glow-idle',
    eyelidTop: 60, eyelidBot: 10, pupilScale: 0.7,
    lookX: 0, lookY: 10,
    label: 'OFFLINE', badge: ''
  }
};

// =====================================================
// RobotFace Class — Manages animated eyes
// =====================================================
class RobotFace {
  constructor() {
    this.currentEmotion = 'idle';

    // Eye elements
    this.irisL = document.getElementById('iris-left');
    this.irisR = document.getElementById('iris-right');
    this.eyelidTopL = document.getElementById('eyelid-top-left');
    this.eyelidTopR = document.getElementById('eyelid-top-right');
    this.eyelidBotL = document.getElementById('eyelid-bot-left');
    this.eyelidBotR = document.getElementById('eyelid-bot-right');
    this.stateBadge = document.getElementById('state-badge');
    this.robotName  = document.querySelector('.robot-name');

    // Timer handles
    this._blinkTimer   = null;
    this._lookTimer    = null;
    this._thinkTimer   = null;
    this._speakTimer   = null;

    // Eye size for clamping pupil movement
    this._eyeSize = 140; // px (must match --eye-size)
    this._maxMove = this._eyeSize * 0.18; // ~25px max movement radius

    this._startIdleAnimations();
  }

  // ---- Apply a named emotion/state ----
  setEmotion(emotion) {
    const cfg = FACE_STATES[emotion] || FACE_STATES.idle;
    this.currentEmotion = emotion;

    // Resolve CSS variable values
    const style = getComputedStyle(document.documentElement);
    const irisColor = style.getPropertyValue(cfg.irisVar).trim() || '#1a6ef5';
    const glowColor = style.getPropertyValue(cfg.glowVar).trim() || 'rgba(26,110,245,0.35)';

    // Update CSS custom properties (drives ambient rings, state badge, name glow)
    document.documentElement.style.setProperty('--iris-current', `var(${cfg.irisVar})`);
    document.documentElement.style.setProperty('--glow-current', `var(${cfg.glowVar})`);

    // Update iris gradient
    [this.irisL, this.irisR].forEach(el => {
      if (!el) return;
      el.style.background = `radial-gradient(circle at 35% 35%,
        rgba(255,255,255,0.3),
        ${irisColor} 40%,
        color-mix(in srgb, ${irisColor} 55%, black) 100%)`;
    });

    // Update eyelids
    this._setEyelids(cfg.eyelidTop, cfg.eyelidBot);

    // Update pupil size
    this._setPupilScale(cfg.pupilScale);

    // Move pupils to state default position
    this._movePupils(cfg.lookX, cfg.lookY, true);

    // Update state badge
    if (this.stateBadge) {
      this.stateBadge.innerText = cfg.label;
      this.stateBadge.style.color = irisColor;
      this.stateBadge.style.borderColor = irisColor;
    }
    if (this.robotName) {
      this.robotName.style.color = irisColor;
      this.robotName.style.textShadow = `0 0 30px ${glowColor}`;
    }

    // Stop all state animations then start the right one
    this._stopAnimations();
    if (emotion === 'idle' || emotion === 'neutral') {
      this._startIdleAnimations();
    } else if (emotion === 'thinking') {
      this._startThinkingAnimation();
    } else if (emotion === 'speaking') {
      this._startSpeakingAnimation();
    } else if (emotion === 'listening') {
      this._startListeningAnimation();
    }
  }

  // ---- Blink (quick eyelid close → open) ----
  blink(doubleBlink = false) {
    const cfg = FACE_STATES[this.currentEmotion] || FACE_STATES.idle;
    this._setEyelids(100, 0);
    setTimeout(() => {
      this._setEyelids(cfg.eyelidTop, cfg.eyelidBot);
      if (doubleBlink) {
        setTimeout(() => {
          this._setEyelids(100, 0);
          setTimeout(() => this._setEyelids(cfg.eyelidTop, cfg.eyelidBot), 110);
        }, 220);
      }
    }, 120);
  }

  // ---- Private: set eyelid heights (% of eye socket) ----
  _setEyelids(top, bot) {
    const pct = h => `${h}%`;
    const applyBorderRadius = (el, isTop) => {
      if (!el) return;
      el.style.height = isTop ? pct(top) : pct(bot);
      // Happy squint — curved eyelid bottom edge
      if (isTop && top > 25) {
        el.style.borderRadius = '0 0 60% 60%';
      } else {
        el.style.borderRadius = isTop ? '0 0 50% 50%' : '50% 50% 0 0';
      }
    };
    applyBorderRadius(this.eyelidTopL, true);
    applyBorderRadius(this.eyelidTopR, true);
    applyBorderRadius(this.eyelidBotL, false);
    applyBorderRadius(this.eyelidBotR, false);
  }

  // ---- Private: move pupils (px offset from center) ----
  _movePupils(x, y, smooth = true) {
    // Clamp to max movement radius
    const dist  = Math.sqrt(x * x + y * y);
    const limit = this._maxMove;
    if (dist > limit) {
      const scale = limit / dist;
      x *= scale; y *= scale;
    }

    const transition = smooth ? 'transform 0.4s cubic-bezier(0.34,1.56,0.64,1)' : 'none';
    [this.irisL, this.irisR].forEach(el => {
      if (!el) return;
      el.style.transition = transition;
      el.style.transform  = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;
    });
  }

  // ---- Private: scale pupil ----
  _setPupilScale(scale) {
    const size = `${Math.round(scale * 48)}%`;
    document.querySelectorAll('.pupil').forEach(el => {
      el.style.width  = size;
      el.style.height = size;
    });
  }

  // ---- Private: stop all interval timers ----
  _stopAnimations() {
    clearTimeout(this._blinkTimer);
    clearTimeout(this._lookTimer);
    clearTimeout(this._thinkTimer);
    clearTimeout(this._speakTimer);
  }

  // ---- Idle: random blinks + random looks ----
  _startIdleAnimations() {
    const scheduleBlink = () => {
      const delay = 2500 + Math.random() * 3500;
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'idle' || this.currentEmotion === 'neutral') {
          this.blink(Math.random() < 0.15); // 15% chance double blink
        }
        scheduleBlink();
      }, delay);
    };
    scheduleBlink();

    const scheduleLook = () => {
      const delay = 4000 + Math.random() * 5000;
      this._lookTimer = setTimeout(() => {
        if (this.currentEmotion === 'idle' || this.currentEmotion === 'neutral') {
          const angle = Math.random() * Math.PI * 2;
          const r = this._maxMove * (0.3 + Math.random() * 0.7);
          const x = Math.cos(angle) * r;
          const y = Math.sin(angle) * r * 0.6; // slightly less vertical
          this._movePupils(x, y);
          // Return to center
          setTimeout(() => {
            if (this.currentEmotion === 'idle' || this.currentEmotion === 'neutral') {
              this._movePupils(0, 0);
            }
          }, 1200 + Math.random() * 1000);
        }
        scheduleLook();
      }, delay);
    };
    scheduleLook();
  }

  // ---- Thinking: pupils drift up-left in pattern ----
  _startThinkingAnimation() {
    const positions = [
      [-20, -18], [-8, -24], [10, -20], [-14, -10], [0, -22], [-20, -18]
    ];
    let idx = 0;
    const move = () => {
      if (this.currentEmotion !== 'thinking') return;
      const [x, y] = positions[idx % positions.length];
      this._movePupils(x + (Math.random() - 0.5) * 4, y + (Math.random() - 0.5) * 3);
      idx++;
      this._thinkTimer = setTimeout(move, 700 + Math.random() * 500);
    };
    move();

    // Occasional blink while thinking
    const scheduleBlink = () => {
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'thinking') { this.blink(); scheduleBlink(); }
      }, 4000 + Math.random() * 3000);
    };
    scheduleBlink();
  }

  // ---- Listening: pupils centered + slight upward tilt, quick blink ----
  _startListeningAnimation() {
    this._movePupils(0, -6);
    const scheduleBlink = () => {
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'listening') { this.blink(); scheduleBlink(); }
      }, 3000 + Math.random() * 2000);
    };
    scheduleBlink();
  }

  // ---- Speaking: subtle rhythmic eye movement ----
  _startSpeakingAnimation() {
    let phase = 0;
    const animate = () => {
      if (this.currentEmotion !== 'speaking') return;
      const x = Math.cos(phase * 0.8) * 4;
      const y = Math.sin(phase) * 3;
      this._movePupils(x, y, false);
      phase += 0.08;
      this._speakTimer = setTimeout(animate, 50);
    };
    animate();

    // Blink occasionally while speaking
    const scheduleBlink = () => {
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'speaking') { this.blink(); scheduleBlink(); }
      }, 3500 + Math.random() * 2500);
    };
    scheduleBlink();
  }
}

// =====================================================
// WebSocket + UI Glue
// =====================================================

// Init face engine
const face = new RobotFace();

// DOM
let socket = null;
const wsStatus      = document.getElementById('ws-status');
const stateBadge    = document.getElementById('state-badge');
const speechBubble  = document.getElementById('speech-bubble');
const bubbleText    = document.getElementById('bubble-text');
const statusHint    = document.getElementById('status-hint');
const appContainer  = document.querySelector('.app-container');
const faceStage     = document.getElementById('face-stage');

// Vitals
const bpValue   = document.getElementById('bp-value');
const spo2Value = document.getElementById('spo2-value');
const hrValue   = document.getElementById('hr-value');
const tempValue = document.getElementById('temp-value');
const vitalCards = {
  blood_pressure: document.getElementById('vital-bp'),
  spo2:           document.getElementById('vital-spo2'),
  heart_rate:     document.getElementById('vital-hr'),
  temperature:    document.getElementById('vital-temp')
};
const cardsList = document.getElementById('content-cards-list');

// Overlays
const telemedOverlay  = document.getElementById('telemed-overlay');
const endTelemedBtn   = document.getElementById('end-telemed-btn');
const alertOverlay    = document.getElementById('reminder-alert-overlay');
const alertTitle      = document.getElementById('reminder-alert-title');
const alertBody       = document.getElementById('reminder-alert-body');
const ackReminderBtn  = document.getElementById('ack-reminder-btn');
let activeReminderId  = null;

// ---- WebSocket ----
const wsUrl = `ws://${window.location.hostname || 'localhost'}:8765`;

function connectWebSocket() {
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    if (wsStatus) {
      wsStatus.classList.add('online');
      wsStatus.querySelector('.status-text').innerText = 'ONLINE';
    }
    setEmotion('happy');
    setTimeout(() => setEmotion('neutral'), 2000);
  };

  socket.onclose = () => {
    if (wsStatus) {
      wsStatus.classList.remove('online');
      wsStatus.querySelector('.status-text').innerText = 'OFFLINE';
    }
    updateState('idle');
    setEmotion('sleepy');
    setTimeout(connectWebSocket, 3000);
  };

  socket.onerror = (e) => console.error('WS error:', e);

  socket.onmessage = (event) => {
    try {
      handleServerMessage(JSON.parse(event.data));
    } catch (ex) {
      console.error('WS parse error:', ex);
    }
  };
}

function handleServerMessage(data) {
  switch (data.type) {
    case 'state_change':    updateState(data.state); break;
    case 'emotion_change':  setEmotion(data.emotion, data.intensity); break;
    case 'transcript':      showBubble(data.text); break;
    case 'countdown':       showCountdown(data.seconds, data.total); break;
    case 'show_card':       renderContentCard(data); break;
    case 'vitals_update':   updateVitalsDisplay(data.vitals); break;
    case 'telemedicine_trigger': showTelemedicineCall(data.reason); break;
  }
}

// ---- Speech Bubble ----
let bubbleTimer = null;
function showBubble(text, durationMs = 5000) {
  if (!text || !text.trim()) return;
  bubbleText.innerText = text;
  speechBubble.classList.add('visible');
  clearTimeout(bubbleTimer);
  bubbleTimer = setTimeout(() => {
    speechBubble.classList.remove('visible');
  }, durationMs);
}
function hideBubble() {
  clearTimeout(bubbleTimer);
  speechBubble.classList.remove('visible');
}

// ---- Thinking-too-long indicator ----
let thinkingTimer = null;
function startThinkingTimer() {
  clearTimeout(thinkingTimer);
  thinkingTimer = setTimeout(() => {
    if (appContainer.classList.contains('state-thinking')) {
      showBubble('🤔 กำลังคิดอยู่นะครับ รอแป๊บนึง...', 6000);
    }
  }, 4000);  // Show after 4s of thinking
}
function clearThinkingTimer() {
  clearTimeout(thinkingTimer);
}


// ---- State Updates ----
const countdownArc = document.getElementById('ptt-countdown-arc');

function showCountdown(seconds, total) {
  if (seconds <= 0) {
    if (countdownArc) {
      countdownArc.classList.remove('active');
      countdownArc.style.setProperty('--countdown-pct', '0%');
    }
    // Reset status hint after countdown
    if (!appContainer.classList.contains('state-thinking') &&
        !appContainer.classList.contains('state-speaking')) {
      statusHint.innerText = 'LISTENING';
    }
    return;
  }
  if (countdownArc) {
    const pct = (seconds / total) * 100;
    countdownArc.style.setProperty('--countdown-pct', pct.toFixed(1) + '%');
    countdownArc.classList.add('active');
  }
  // Show remaining seconds in status hint
  statusHint.innerText = `${seconds}s`;
}

function updateState(state) {
  appContainer.classList.remove('state-listening', 'state-thinking', 'state-speaking');
  if (state !== 'idle') appContainer.classList.add(`state-${state}`);

  // Clear countdown arc
  countdownArc.classList.remove('active');
  countdownArc.style.setProperty('--countdown-pct', '0%');

  clearThinkingTimer();

  if (state === 'listening') {
    isPttPressed = true;
    statusHint.innerText = 'LISTENING';
    setEmotion('listening');
    hideBubble();
  } else if (state === 'thinking') {
    isPttPressed = false;
    statusHint.innerText = 'THINKING';
    setEmotion('thinking');
    startThinkingTimer();
  } else if (state === 'speaking') {
    isPttPressed = false;
    statusHint.innerText = 'SPEAKING';
    hideBubble();
    setEmotion('speaking');
  } else {
    isPttPressed = false;
    statusHint.innerText = 'READY';
    setEmotion('neutral');
  }
}

// ---- Emotion Updates ----
function setEmotion(emotion, intensity = 1.0) {
  face.setEmotion(emotion);
}

// ---- PTT (face-tap) ----
let isPttPressed = false;

function pressPTT() {
  if (isPttPressed) return;
  isPttPressed = true;
  statusHint.innerText = 'LISTENING';
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ptt_press' }));
}

function releasePTT() {
  if (!isPttPressed) return;
  isPttPressed = false;
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ptt_release' }));
}

function toggleMic() {
  const state = appContainer.className;
  if (state.includes('state-listening')) {
    // Already listening — don't release, VAD handles it automatically
    return;
  }
  if (state.includes('state-thinking')) {
    // Already processing — ignore tap
    return;
  }
  pressPTT();
}

// Tap face-stage to toggle talk
faceStage.addEventListener('click', (e) => { e.preventDefault(); toggleMic(); });
faceStage.addEventListener('touchend', (e) => { e.preventDefault(); toggleMic(); });

// Test Speaker (now top-left)
const testAudioBtn = document.getElementById('test-audio-btn');
if (testAudioBtn) {
  testAudioBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'test_speaker' }));
  });
}

// ---- Cards ----
function renderContentCard(data) {
  const placeholder = cardsList.querySelector('.placeholder-card');
  if (placeholder) cardsList.innerHTML = '';

  if (data.card_type === 'reminder_alert') {
    const rData = JSON.parse(data.payload);
    activeReminderId = rData.id;
    alertTitle.innerText = data.title;
    alertBody.innerText  = data.body;
    alertOverlay.style.display = 'flex';
    setEmotion('surprised');
    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain= ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = 660;
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      osc.start(); osc.stop(ctx.currentTime + 0.3);
    } catch(e) {}
    return;
  }

  const card = document.createElement('div');
  card.className = `dynamic-card card-${data.card_type}`;
  const h3 = document.createElement('h3'); h3.innerText = data.title;
  const p  = document.createElement('p');  p.innerText  = data.body;
  card.appendChild(h3); card.appendChild(p);
  cardsList.insertBefore(card, cardsList.firstChild);
}

// ---- Vitals ----
function updateVitalsDisplay(vitalsList) {
  const latest = {};
  vitalsList.forEach(v => { if (!latest[v.type]) latest[v.type] = v; });
  ['blood_pressure','spo2','heart_rate','temperature'].forEach(t => {
    const data = latest[t];
    const card = vitalCards[t];
    card.classList.remove('status-high','status-low');
    if (data) {
      card.querySelector('.vital-value').innerText = data.value;
      if (data.status === 'high' || data.status === 'critical') card.classList.add('status-high');
      else if (data.status === 'low') card.classList.add('status-low');
    }
  });
}

// ---- Telemedicine ----
function showTelemedicineCall(reason) {
  telemedOverlay.style.display = 'flex';
  setEmotion('concerned');
  transcriptText.innerText = 'กำลังเปิดกล้องระบบแพทย์ทางไกล Socare...';
}
endTelemedBtn.addEventListener('click', () => {
  telemedOverlay.style.display = 'none';
  setEmotion('neutral');
});

// ---- Reminder ACK ----
ackReminderBtn.addEventListener('click', () => {
  alertOverlay.style.display = 'none';
  if (activeReminderId && socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'ack_reminder', reminder_id: activeReminderId }));
  }
  activeReminderId = null;
  setEmotion('happy');
  setTimeout(() => setEmotion('neutral'), 3000);
});

// ---- Boot ----
window.addEventListener('load', () => {
  connectWebSocket();
});
