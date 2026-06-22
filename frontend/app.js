// =====================================================
// JARVIS Robot Face — Animation Engine + WebSocket
// =====================================================

// ---- State Definitions — every state tells a story through the eyes ----
const FACE_STATES = {
  idle: {
    // Calm, resting — eyes forward, relaxed
    irisVar: '--iris-idle', glowVar: '--glow-idle',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.0,
    lookX: 0, lookY: 0, label: 'STANDBY'
  },
  listening: {
    // WIDE OPEN — dilated pupils, full attention
    // "ฉันกำลังฟังคุณอยู่ ไม่พลาดทุกคำ"
    irisVar: '--iris-listen', glowVar: '--glow-listen',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.28,
    lookX: 0, lookY: -5, label: 'LISTENING'
  },
  thinking: {
    // SQUINTING — contracted pupils, concentration, scanning memory
    // "กำลังค้นหาคำตอบ..."
    irisVar: '--iris-think', glowVar: '--glow-think',
    eyelidTop: 30, eyelidBot: 0, pupilScale: 0.65,
    lookX: -20, lookY: -20, label: 'THINKING'
  },
  speaking: {
    // Engaged eye contact — pupils normal, slight focus
    // "ฉันกำลังบอกคุณ"
    irisVar: '--iris-speak', glowVar: '--glow-speak',
    eyelidTop: 4, eyelidBot: 0, pupilScale: 1.08,
    lookX: 0, lookY: 0, label: 'SPEAKING'
  },
  happy: {
    // FULL EYE SMILE — both lids squint (Duchenne smile)
    // "ยิ้มถึงตา ความสุขจริงๆ"
    irisVar: '--iris-happy', glowVar: '--glow-happy',
    eyelidTop: 42, eyelidBot: 36, pupilScale: 1.18,
    lookX: 0, lookY: 7, label: 'HAPPY'
  },
  concerned: {
    // Furrowed brow, pupils looking slightly down
    // "เป็นห่วงคุณ"
    irisVar: '--iris-concerned', glowVar: '--glow-concerned',
    eyelidTop: 24, eyelidBot: 0, pupilScale: 0.88,
    lookX: 0, lookY: 16, label: 'CONCERNED'
  },
  sad: {
    // Heavy drooped eyelids, pupils far down — genuine sadness
    // "รู้สึกเศร้า"
    irisVar: '--iris-sad', glowVar: '--glow-idle',
    eyelidTop: 45, eyelidBot: 0, pupilScale: 0.82,
    lookX: -6, lookY: 22, label: 'SAD'
  },
  surprised: {
    // EYES SNAP WIDE — max dilation, pupils shoot up
    // "ตกใจ! ไม่คาดคิด!"
    irisVar: '--iris-happy', glowVar: '--glow-happy',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.45,
    lookX: 0, lookY: -9, label: 'SURPRISED'
  },
  neutral: {
    irisVar: '--iris-idle', glowVar: '--glow-idle',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.0,
    lookX: 0, lookY: 0, label: 'STANDBY'
  },
  sleepy: {
    // Half-closed — low energy / offline
    irisVar: '--iris-sleepy', glowVar: '--glow-idle',
    eyelidTop: 58, eyelidBot: 8, pupilScale: 0.7,
    lookX: 0, lookY: 10, label: 'OFFLINE'
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

    // Mouth + Eyebrow elements
    this.mouthPath = document.getElementById('mouth-path');
    this.browL     = document.getElementById('brow-path-left');
    this.browR     = document.getElementById('brow-path-right');

    // Timer handles
    this._blinkTimer   = null;
    this._lookTimer    = null;
    this._thinkTimer   = null;
    this._speakTimer   = null;
    this._mouthTimer   = null;

    // Eye size for clamping pupil movement
    this._eyeSize = 140;
    this._maxMove = this._eyeSize * 0.18;

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

    // Update mouth shape for this emotion
    this._setMouthForEmotion(emotion, irisColor, glowColor);

    // Update eyebrows for this emotion
    this._setEyebrowsForEmotion(emotion, irisColor, glowColor);

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

  // ---- Mouth shapes per emotion ----
  _setMouthForEmotion(emotion, irisColor, glowColor) {
    // SVG paths — viewBox 0 0 80 30, center = 40,15
    const shapes = {
      idle:      'M 15,16 Q 40,20 65,16',    // Relaxed slight smile
      neutral:   'M 15,16 Q 40,20 65,16',
      listening: 'M 12,14 Q 40,23 68,14',    // Open/attentive
      thinking:  'M 18,20 Q 40,12 62,20',    // Tight frown — concentrating
      speaking:  'M 12,15 Q 40,23 68,15',    // Lightly open (resting speak)
      happy:     'M 8,9  Q 40,32 72,9',      // Big genuine smile
      concerned: 'M 16,22 Q 40,11 64,22',    // Clear frown — worried
      sad:       'M 12,25 Q 40,7  68,25',    // Deep sad frown
      surprised: 'M 33,9  Q 40,28 47,9',     // Small oval — open O
      sleepy:    'M 22,16 Q 40,17 58,16',    // Almost flat — low energy
    };
    const d = shapes[emotion] || shapes.idle;
    this._setMouth(d, irisColor, glowColor);
  }

  // ---- Set mouth SVG path + color ----
  _setMouth(d, color, glow) {
    if (!this.mouthPath) return;
    this.mouthPath.setAttribute('d', d);
    if (color) {
      this.mouthPath.style.stroke = color;
      this.mouthPath.style.filter = `drop-shadow(0 0 5px ${glow || color})`;
    }
  }

  // ---- Eyebrow shapes per emotion ----
  // viewBox 0 0 60 20. Left brow: inner edge = RIGHT side. Right brow: inner edge = LEFT side.
  _setEyebrowsForEmotion(emotion, irisColor, glowColor) {
    const L = {
      idle:      'M 4,14 Q 30,8  56,12',   // Gentle arch — relaxed
      neutral:   'M 4,14 Q 30,8  56,12',
      listening: 'M 4,9  Q 30,4  56,8',    // Both raised — attentive
      thinking:  'M 4,10 Q 30,7  56,15',   // Outer drops, inner high — furrowed focus
      speaking:  'M 4,11 Q 30,6  56,10',   // Slightly raised — engaged
      happy:     'M 4,7  Q 30,2  56,7',    // High arched — joy
      concerned: 'M 4,12 Q 30,5  56,16',   // Outer drops sharply — worried
      sad:       'M 4,8  Q 30,10 56,15',   // Drooped outward — sad
      surprised: 'M 4,5  Q 30,1  56,5',    // MAX raised — shock
      sleepy:    'M 4,16 Q 30,13 56,15',   // Low and flat — sleepy
    };
    const R = {  // Mirror of L (inner edge is the LEFT side now)
      idle:      'M 4,12 Q 30,8  56,14',
      neutral:   'M 4,12 Q 30,8  56,14',
      listening: 'M 4,8  Q 30,4  56,9',
      thinking:  'M 4,15 Q 30,7  56,10',   // Mirror of left furrowed
      speaking:  'M 4,10 Q 30,6  56,11',
      happy:     'M 4,7  Q 30,2  56,7',
      concerned: 'M 4,16 Q 30,5  56,12',   // Mirror
      sad:       'M 4,15 Q 30,10 56,8',
      surprised: 'M 4,5  Q 30,1  56,5',
      sleepy:    'M 4,15 Q 30,13 56,16',
    };
    const dL = L[emotion] || L.idle;
    const dR = R[emotion] || R.idle;
    [this.browL, this.browR].forEach((el, i) => {
      if (!el) return;
      el.setAttribute('d', i === 0 ? dL : dR);
      el.style.stroke = irisColor;
      el.style.filter = `drop-shadow(0 0 5px ${glowColor})`;
    });
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
    clearTimeout(this._mouthTimer);
  }

  // ---- Idle: natural wandering gaze + occasional blink ----
  _startIdleAnimations() {
    const scheduleBlink = () => {
      this._blinkTimer = setTimeout(() => {
        const em = this.currentEmotion;
        if (em === 'idle' || em === 'neutral' || em === 'sleepy') {
          this.blink(Math.random() < 0.12);
        }
        scheduleBlink();
      }, 2800 + Math.random() * 3200);
    };
    scheduleBlink();

    const scheduleLook = () => {
      this._lookTimer = setTimeout(() => {
        const em = this.currentEmotion;
        if (em === 'idle' || em === 'neutral' || em === 'sleepy') {
          const angle = Math.random() * Math.PI * 2;
          const r = this._maxMove * (0.25 + Math.random() * 0.65);
          this._movePupils(Math.cos(angle) * r, Math.sin(angle) * r * 0.55);
          setTimeout(() => {
            if (this.currentEmotion === 'idle' || this.currentEmotion === 'neutral' || this.currentEmotion === 'sleepy') {
              this._movePupils(0, 0);
            }
          }, 1000 + Math.random() * 1200);
        }
        scheduleLook();
      }, 4500 + Math.random() * 5000);
    };
    scheduleLook();
  }

  // ---- Thinking: rapid saccades — scanning memory like REM sleep ----
  _startThinkingAnimation() {
    // Pattern: dart up-left → right → left → center-up → repeat
    // Mimics actual human "thinking" eye movement
    const scanPath = [
      [-22, -20], [20, -22], [-14, -16], [18, -18],
      [-6,  -24], [14, -20], [-20, -12], [0,   -22],
      [-16, -18], [22, -16]
    ];
    let idx = 0;
    const scan = () => {
      if (this.currentEmotion !== 'thinking') return;
      const [x, y] = scanPath[idx % scanPath.length];
      // Jitter for natural scanning
      this._movePupils(x + (Math.random()-0.5)*3, y + (Math.random()-0.5)*2);
      idx++;
      // Fast scan then pause — like reading
      const delay = idx % 3 === 0
        ? 900 + Math.random() * 500   // pause
        : 380 + Math.random() * 280;  // quick dart
      this._thinkTimer = setTimeout(scan, delay);
    };
    scan();

    // Less blinking when thinking hard
    const blink = () => {
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'thinking') { this.blink(); blink(); }
      }, 4500 + Math.random() * 3500);
    };
    blink();
  }

  // ---- Listening: wide-eyed attention with micro-tracking ----
  _startListeningAnimation() {
    // Eyes wide, focused forward — micro-movements show active attention
    let phase = 0;
    const track = () => {
      if (this.currentEmotion !== 'listening') return;
      // Tiny 1-2px micro-movements: subtle tracking of speaker
      const x = Math.sin(phase * 0.6) * 2.5;
      const y = -5 + Math.cos(phase * 0.4) * 1.8;
      this._movePupils(x, y, false);
      phase += 0.12;
      this._lookTimer = setTimeout(track, 70);
    };
    track();

    // Fewer blinks = more attentive (humans blink less when focused)
    const blink = () => {
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'listening') { this.blink(); blink(); }
      }, 5000 + Math.random() * 4000);
    };
    blink();
  }

  // ---- Speaking: natural conversational eye movement ----
  _startSpeakingAnimation() {
    // Natural speech: make "eye contact" center, then glance away, then back
    const gazePoints = [
      [0, 0], [3, -2], [-2, 1], [1, -3],
      [0, 0], [-3, -1], [2, 2], [0, -1],
      [0, 0], [4, -1], [-1, 2], [0, 0]
    ];
    let idx = 0;
    const gaze = () => {
      if (this.currentEmotion !== 'speaking') return;
      const [x, y] = gazePoints[idx % gazePoints.length];
      this._movePupils(x + (Math.random()-0.5)*1.5, y + (Math.random()-0.5)*1.5);
      idx++;
      this._speakTimer = setTimeout(gaze, 350 + Math.random() * 250);
    };
    gaze();

    // Mouth: alternate open/closed to simulate talking
    const style = getComputedStyle(document.documentElement);
    const irisColor = style.getPropertyValue('--iris-speak').trim();
    const glowColor = style.getPropertyValue('--glow-speak').trim();
    let mouthOpen = false;
    const animateMouth = () => {
      if (this.currentEmotion !== 'speaking') {
        // Reset mouth to neutral smile when done speaking
        this._setMouth('M 15,16 Q 40,20 65,16', irisColor, glowColor);
        return;
      }
      mouthOpen = !mouthOpen;
      // Vary open amount for natural speech rhythm
      const openAmt = mouthOpen ? (18 + Math.random() * 10) : 15;
      const closeAmt = mouthOpen ? (12 - Math.random() * 4) : 20;
      const d = mouthOpen
        ? `M 15,${closeAmt} Q 40,${openAmt + 8} 65,${closeAmt}`
        : `M 12,15 Q 40,22 68,15`;
      this._setMouth(d, irisColor, glowColor);
      this._mouthTimer = setTimeout(animateMouth, 110 + Math.random() * 90);
    };
    animateMouth();

    // Normal blink rate while speaking
    const blink = () => {
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'speaking') { this.blink(); blink(); }
      }, 3200 + Math.random() * 2000);
    };
    blink();
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
    case 'telemedicine_trigger': showTelemedicineCall(data.reason, data.url); break;
    case 'camera_preview':  showCameraPreview(data.image); break;
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

// Clear History
const clearHistoryBtn = document.getElementById('clear-history-btn');
if (clearHistoryBtn) {
  clearHistoryBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (confirm('ลบประวัติการสนทนาทั้งหมด?')) {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'clear_history' }));
    }
  });
}

// Camera Button
const cameraBtn = document.getElementById('camera-btn');
if (cameraBtn) {
  cameraBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'capture_camera' }));
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

// ---- Camera Preview ----
function showCameraPreview(base64Image) {
  let preview = document.getElementById('camera-preview');
  if (!preview) {
    preview = document.createElement('div');
    preview.id = 'camera-preview';
    preview.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:200;border-radius:16px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.8);border:2px solid rgba(0,200,255,0.3);max-width:320px;max-height:240px;';
    const img = document.createElement('img');
    img.id = 'camera-preview-img';
    img.style.cssText = 'width:100%;height:auto;display:block;';
    preview.appendChild(img);
    const label = document.createElement('div');
    label.style.cssText = 'position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,0.7);color:#00d4ff;text-align:center;padding:6px;font-size:13px;font-family:Sarabun,sans-serif;';
    label.innerText = '📷 กล้อง';
    preview.appendChild(label);
    document.body.appendChild(preview);
  }
  document.getElementById('camera-preview-img').src = 'data:image/jpeg;base64,' + base64Image;
  preview.style.display = 'block';
  setTimeout(() => { preview.style.display = 'none'; }, 5000);
}

// ---- Telemedicine ----
function showTelemedicineCall(reason, url) {
  telemedOverlay.style.display = 'flex';
  setEmotion('concerned');
  transcriptText.innerText = 'กำลังเปิดกล้องระบบแพทย์ทางไกล Socare...';
  // Open Socare video call in iframe
  const videoFrame = document.getElementById('socare-video-frame');
  if (videoFrame && url) {
    videoFrame.src = url;
    videoFrame.style.display = 'block';
  }
}
endTelemedBtn.addEventListener('click', () => {
  telemedOverlay.style.display = 'none';
  setEmotion('neutral');
  // Clear iframe
  const videoFrame = document.getElementById('socare-video-frame');
  if (videoFrame) { videoFrame.src = ''; videoFrame.style.display = 'none'; }
  const mockView = document.getElementById('telemed-mock');
  if (mockView) mockView.style.display = 'flex';
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
