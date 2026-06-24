// =====================================================
// JARVIS Robot Face — Animation Engine + WebSocket
// v2.0 — Natural Conversation + Full Animation
// =====================================================

// ---- State Definitions — every state tells a story through the eyes ----
const FACE_STATES = {
  idle: {
    irisVar: '--iris-idle', glowVar: '--glow-idle',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.0,
    lookX: 0, lookY: 0, label: 'STANDBY',
    headTilt: 0, headNod: 0
  },
  listening: {
    irisVar: '--iris-listen', glowVar: '--glow-listen',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.28,
    lookX: 0, lookY: -5, label: 'LISTENING',
    headTilt: 3, headNod: -2   // slight right tilt = attentive
  },
  thinking: {
    irisVar: '--iris-think', glowVar: '--glow-think',
    eyelidTop: 12, eyelidBot: 0, pupilScale: 0.95,
    lookX: -10, lookY: -10, label: 'THINKING',
    headTilt: -4, headNod: -3  // left tilt = thinking
  },
  speaking: {
    irisVar: '--iris-speak', glowVar: '--glow-speak',
    eyelidTop: 4, eyelidBot: 0, pupilScale: 1.08,
    lookX: 0, lookY: 0, label: 'SPEAKING',
    headTilt: 0, headNod: 0
  },
  happy: {
    irisVar: '--iris-happy', glowVar: '--glow-happy',
    eyelidTop: 42, eyelidBot: 36, pupilScale: 1.18,
    lookX: 0, lookY: 7, label: 'HAPPY',
    headTilt: 5, headNod: 4   // happy head bob
  },
  concerned: {
    irisVar: '--iris-concerned', glowVar: '--glow-concerned',
    eyelidTop: 24, eyelidBot: 0, pupilScale: 0.88,
    lookX: 0, lookY: 16, label: 'CONCERNED',
    headTilt: -2, headNod: 2
  },
  sad: {
    irisVar: '--iris-sad', glowVar: '--glow-idle',
    eyelidTop: 45, eyelidBot: 0, pupilScale: 0.82,
    lookX: -6, lookY: 22, label: 'SAD',
    headTilt: -3, headNod: 6
  },
  surprised: {
    irisVar: '--iris-happy', glowVar: '--glow-happy',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.45,
    lookX: 0, lookY: -9, label: 'SURPRISED',
    headTilt: 0, headNod: -5  // slight jerk back
  },
  neutral: {
    irisVar: '--iris-idle', glowVar: '--glow-idle',
    eyelidTop: 0, eyelidBot: 0, pupilScale: 1.0,
    lookX: 0, lookY: 0, label: 'STANDBY',
    headTilt: 0, headNod: 0
  },
  sleepy: {
    irisVar: '--iris-sleepy', glowVar: '--glow-idle',
    eyelidTop: 100, eyelidBot: 0, pupilScale: 0.0,
    lookX: 0, lookY: 0, label: 'SLEEPING',
    headTilt: 0, headNod: 12  // drooping head more down
  }
};

// =====================================================
// RobotFace Class — Animated eyes + head + mouth
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

    // Head + mouth
    this.robotHead = document.querySelector('.robot-head');
    this.mouthPath = document.getElementById('mouth-path');
    this.browL     = document.getElementById('brow-path-left');
    this.browR     = document.getElementById('brow-path-right');

    // Timer handles
    this._blinkTimer   = null;
    this._lookTimer    = null;
    this._thinkTimer   = null;
    this._speakTimer   = null;
    this._mouthTimer   = null;
    this._headTimer    = null;

    // Eye size for clamping pupil movement
    this._eyeSize = 140;
    this._maxMove = this._eyeSize * 0.18;

    // Lip sync state
    this._lastAudioAmp  = 0;    // smoothed Gemini audio amplitude (0-100)
    this._lastMicAmp    = 0;    // smoothed mic amplitude (0-100)
    this._lipSyncTimer  = null;

    // Head tilt state
    this._headTiltCurrent = 0;
    this._headNodCurrent  = 0;

    this._startIdleAnimations();
  }

  // ---- Apply a named emotion/state ----
  setEmotion(emotion) {
    const cfg = FACE_STATES[emotion] || FACE_STATES.idle;
    this.currentEmotion = emotion;

    const style = getComputedStyle(document.documentElement);
    const irisColor = style.getPropertyValue(cfg.irisVar).trim() || '#1a6ef5';
    const glowColor = style.getPropertyValue(cfg.glowVar).trim() || 'rgba(26,110,245,0.35)';

    document.documentElement.style.setProperty('--iris-current', `var(${cfg.irisVar})`);
    document.documentElement.style.setProperty('--glow-current', `var(${cfg.glowVar})`);

    [this.irisL, this.irisR].forEach(el => {
      if (!el) return;
      el.style.background = `radial-gradient(circle at 35% 35%,
        rgba(255,255,255,0.3),
        ${irisColor} 40%,
        color-mix(in srgb, ${irisColor} 55%, black) 100%)`;
    });

    this._setEyelids(cfg.eyelidTop, cfg.eyelidBot);
    this._setPupilScale(cfg.pupilScale);
    this._movePupils(cfg.lookX, cfg.lookY, true);

    if (this.stateBadge) {
      this.stateBadge.innerText = cfg.label;
      this.stateBadge.style.color = irisColor;
      this.stateBadge.style.borderColor = irisColor;
    }
    if (this.robotName) {
      this.robotName.style.color = irisColor;
      this.robotName.style.textShadow = `0 0 30px ${glowColor}`;
    }

    this._setMouthForEmotion(emotion, irisColor, glowColor);
    this._setEyebrowsForEmotion(emotion, irisColor, glowColor);

    // Animate head tilt to target position
    this._animateHeadTilt(cfg.headTilt, cfg.headNod);

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

  // ---- Head tilt/nod animation ----
  _animateHeadTilt(targetTilt, targetNod) {
    if (!this.robotHead) return;
    const duration = 400; // ms
    const startTilt = this._headTiltCurrent;
    const startNod  = this._headNodCurrent;
    const startTime = performance.now();

    const animate = (now) => {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const ease = 1 - Math.pow(1 - t, 3);

      const tilt = startTilt + (targetTilt - startTilt) * ease;
      const nod  = startNod  + (targetNod  - startNod)  * ease;

      this._headTiltCurrent = tilt;
      this._headNodCurrent  = nod;
      this._applyHeadTransform(tilt, nod);

      if (t < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }

  _applyHeadTransform(tilt, nod, extraScale = 1) {
    if (!this.robotHead) return;
    this.robotHead.style.transform =
      `rotate(${tilt}deg) translateY(${nod}px) scale(${extraScale})`;
  }

  // ---- Wake word flash: quick scale pop ----
  wakeWordFlash() {
    if (!this.robotHead) return;
    let t = 0;
    const animate = () => {
      t += 0.08;
      if (t > 1) {
        this._applyHeadTransform(this._headTiltCurrent, this._headNodCurrent, 1);
        return;
      }
      const scale = 1 + Math.sin(t * Math.PI) * 0.06;
      this._applyHeadTransform(this._headTiltCurrent, this._headNodCurrent, scale);
      requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }

  // ---- Lip sync from real audio amplitude ----
  updateAudioAmplitude(value) {
    // Smooth the amplitude with exponential moving average
    this._lastAudioAmp = this._lastAudioAmp * 0.5 + value * 0.5;
    if (this.currentEmotion === 'speaking') {
      this._applyLipSync(this._lastAudioAmp);
    }
  }

  updateMicAmplitude(value) {
    this._lastMicAmp = this._lastMicAmp * 0.4 + value * 0.6;
  }

  _applyLipSync(amp) {
    const style = getComputedStyle(document.documentElement);
    const irisColor = style.getPropertyValue('--iris-speak').trim();
    const glowColor = style.getPropertyValue('--glow-speak').trim();

    // Map amplitude 0-100 to mouth open amount
    const openY  = 15 + (amp / 100) * 12;   // 15 to 27
    const closeY = 15 - (amp / 100) * 4;    // 15 to 11

    const d = amp > 5
      ? `M 14,${closeY.toFixed(1)} Q 40,${openY.toFixed(1)} 66,${closeY.toFixed(1)}`
      : `M 12,15 Q 40,21 68,15`;

    this._setMouth(d, irisColor, glowColor);

    // Scale ambient rings with amplitude
    const ringScale = 1 + (amp / 100) * 0.12;
    document.querySelectorAll('.ambient-ring').forEach(el => {
      el.style.transform = `scale(${ringScale})`;
    });
  }

  // ---- Waveform bars for listening state (mic amplitude) ----
  updateMicWaveform(amp) {
    const bars = document.querySelectorAll('#listen-bars span');
    if (!bars.length) return;
    bars.forEach((bar, i) => {
      const offset = Math.sin((Date.now() / 120) + i * 0.7) * 0.5 + 0.5;
      const h = amp > 5
        ? 4 + (amp / 100) * 22 * offset
        : 4 + Math.random() * 3;
      bar.style.height = `${h}px`;
    });
  }

  // ---- Mouth shapes per emotion ----
  _setMouthForEmotion(emotion, irisColor, glowColor) {
    const shapes = {
      idle:      'M 15,16 Q 40,20 65,16',
      neutral:   'M 15,16 Q 40,20 65,16',
      listening: 'M 12,14 Q 40,23 68,14',
      thinking:  'M 20,16 Q 40,18 60,16',
      speaking:  'M 12,15 Q 40,23 68,15',
      happy:     'M 8,9  Q 40,32 72,9',
      concerned: 'M 16,22 Q 40,11 64,22',
      sad:       'M 12,25 Q 40,7  68,25',
      surprised: 'M 33,9  Q 40,28 47,9',
      sleepy:    'M 22,16 Q 40,17 58,16',
    };
    this._setMouth(shapes[emotion] || shapes.idle, irisColor, glowColor);
  }

  _setMouth(d, color, glow) {
    if (!this.mouthPath) return;
    this.mouthPath.setAttribute('d', d);
    if (color) {
      this.mouthPath.style.stroke = color;
      // Removed filter to fix Mali GPU drop-shadow border bug
    }
  }

  // ---- Eyebrow shapes per emotion ----
  _setEyebrowsForEmotion(emotion, irisColor, glowColor) {
    const L = {
      idle:      'M 4,14 Q 30,8  56,12',
      neutral:   'M 4,14 Q 30,8  56,12',
      listening: 'M 4,9  Q 30,4  56,8',
      thinking:  'M 4,10 Q 30,6  56,10',
      speaking:  'M 4,11 Q 30,6  56,10',
      happy:     'M 4,7  Q 30,2  56,7',
      concerned: 'M 4,12 Q 30,5  56,16',
      sad:       'M 4,8  Q 30,10 56,15',
      surprised: 'M 4,5  Q 30,1  56,5',
      sleepy:    'M 4,16 Q 30,13 56,15',
    };
    const R = {
      idle:      'M 4,12 Q 30,8  56,14',
      neutral:   'M 4,12 Q 30,8  56,14',
      listening: 'M 4,8  Q 30,4  56,9',
      thinking:  'M 4,14 Q 30,10 56,14',
      speaking:  'M 4,10 Q 30,6  56,11',
      happy:     'M 4,7  Q 30,2  56,7',
      concerned: 'M 4,16 Q 30,5  56,12',
      sad:       'M 4,15 Q 30,10 56,8',
      surprised: 'M 4,5  Q 30,1  56,5',
      sleepy:    'M 4,15 Q 30,13 56,16',
    };
    [this.browL, this.browR].forEach((el, i) => {
      if (!el) return;
      el.setAttribute('d', i === 0 ? (L[emotion] || L.idle) : (R[emotion] || R.idle));
      el.style.stroke = irisColor;
      // Removed filter to fix Mali GPU drop-shadow border bug
    });
  }

  // ---- Blink ----
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

  _setEyelids(top, bot) {
    const pct = h => `${h}%`;
    const applyBorderRadius = (el, isTop) => {
      if (!el) return;
      el.style.height = isTop ? pct(top) : pct(bot);
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

  _movePupils(x, y, smooth = true) {
    const dist  = Math.sqrt(x * x + y * y);
    const limit = this._maxMove;
    if (dist > limit) { const s = limit / dist; x *= s; y *= s; }
    const transition = smooth ? 'transform 0.4s cubic-bezier(0.34,1.56,0.64,1)' : 'none';
    [this.irisL, this.irisR].forEach(el => {
      if (!el) return;
      el.style.transition = transition;
      el.style.transform  = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;
    });
  }

  _setPupilScale(scale) {
    const size = `${Math.round(scale * 48)}%`;
    document.querySelectorAll('.pupil').forEach(el => {
      el.style.width  = size;
      el.style.height = size;
    });
  }

  _stopAnimations() {
    clearTimeout(this._blinkTimer);
    clearTimeout(this._lookTimer);
    clearTimeout(this._thinkTimer);
    clearTimeout(this._speakTimer);
    clearTimeout(this._mouthTimer);
    clearInterval(this._lipSyncTimer);
    clearTimeout(this._headTimer);
  }

  // ---- Idle animations ----
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
            if (this.currentEmotion === 'idle' || this.currentEmotion === 'neutral') {
              this._movePupils(0, 0);
            }
          }, 1000 + Math.random() * 1200);

          // Occasionally do a subtle head drift in idle
          const driftTilt = (Math.random() - 0.5) * 3;
          this._animateHeadTilt(driftTilt, 0);
          setTimeout(() => this._animateHeadTilt(0, 0), 2500);
        }
        scheduleLook();
      }, 4500 + Math.random() * 5000);
    };
    scheduleLook();
  }

  // ---- Thinking: rapid saccades ----
  _startThinkingAnimation() {
    const scanPath = [
      [-22, -20], [20, -22], [-14, -16], [18, -18],
      [-6,  -24], [14, -20], [-20, -12], [0,   -22],
      [-16, -18], [22, -16]
    ];
    let idx = 0;
    const scan = () => {
      if (this.currentEmotion !== 'thinking') return;
      const [x, y] = scanPath[idx % scanPath.length];
      this._movePupils(x + (Math.random()-0.5)*3, y + (Math.random()-0.5)*2);
      idx++;

      // Head micro-drift while thinking
      if (idx % 4 === 0) {
        const driftTilt = -4 + (Math.random() - 0.5) * 2;
        this._animateHeadTilt(driftTilt, -3 + (Math.random()-0.5)*2);
      }

      const delay = idx % 3 === 0
        ? 900 + Math.random() * 500
        : 380 + Math.random() * 280;
      this._thinkTimer = setTimeout(scan, delay);
    };
    scan();

    const blink = () => {
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'thinking') { this.blink(); blink(); }
      }, 4500 + Math.random() * 3500);
    };
    blink();
  }

  // ---- Listening: wide-eyed + waveform ----
  _startListeningAnimation() {
    let phase = 0;
    const track = () => {
      if (this.currentEmotion !== 'listening') return;
      const x = Math.sin(phase * 0.6) * 2.5;
      const y = -5 + Math.cos(phase * 0.4) * 1.8;
      this._movePupils(x, y, false);

      // Update waveform bars from mic amplitude
      this.updateMicWaveform(this._lastMicAmp);

      phase += 0.12;
      this._lookTimer = setTimeout(track, 70);
    };
    track();

    // Lean-in head nod when listening
    this._animateHeadTilt(3, -2);

    const blink = () => {
      this._blinkTimer = setTimeout(() => {
        if (this.currentEmotion === 'listening') { this.blink(); blink(); }
      }, 5000 + Math.random() * 4000);
    };
    blink();
  }

  // ---- Speaking: eye contact + real lip sync ----
  _startSpeakingAnimation() {
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

    // Real lip sync driven by audio_amplitude messages (see updateAudioAmplitude)
    // Fallback animated mouth if no amplitude data comes in
    const style = getComputedStyle(document.documentElement);
    const irisColor = style.getPropertyValue('--iris-speak').trim();
    const glowColor = style.getPropertyValue('--glow-speak').trim();

    let fallbackActive = true;
    const fallbackMouth = () => {
      if (this.currentEmotion !== 'speaking') {
        this._setMouth('M 15,16 Q 40,20 65,16', irisColor, glowColor);
        document.querySelectorAll('.ambient-ring').forEach(el => el.style.transform = '');
        return;
      }
      // Only animate if no real amplitude (prevents fighting with lip sync)
      if (this._lastAudioAmp < 2) {
        const open = Math.random() > 0.45;
        const openAmt  = open ? (17 + Math.random() * 8) : 15;
        const closeAmt = open ? (12 - Math.random() * 3) : 19;
        const d = open
          ? `M 14,${closeAmt} Q 40,${openAmt + 7} 66,${closeAmt}`
          : `M 12,15 Q 40,22 68,15`;
        this._setMouth(d, irisColor, glowColor);
      }
      this._mouthTimer = setTimeout(fallbackMouth, 120 + Math.random() * 100);
    };
    fallbackMouth();

    // Head sway while speaking — subtle life-like movement
    let headPhase = 0;
    const headSway = () => {
      if (this.currentEmotion !== 'speaking') return;
      headPhase += 0.04;
      const tilt = Math.sin(headPhase) * 1.5;
      const nod  = Math.sin(headPhase * 1.3) * 1.0;
      this._applyHeadTransform(tilt, nod);
      this._headTimer = setTimeout(headSway, 50);
    };
    headSway();

    // Blink while speaking
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
    case 'state_change':      updateState(data.state); break;
    case 'emotion_change':    setEmotion(data.emotion, data.intensity); break;
    case 'transcript':        showBubble(data.text); break;
    case 'countdown':         showCountdown(data.seconds, data.total); break;
    case 'show_card':         renderContentCard(data); break;
    case 'vitals_update':     updateVitalsDisplay(data.vitals); break;
    case 'telemedicine_trigger': showTelemedicineCall(data.reason, data.url); break;
    case 'telemedicine_end_trigger': endTelemedicineCall(); break;
    case 'camera_preview':    showCameraPreview(data.image); break;
    case 'audio_amplitude':   handleAudioAmplitude(data.value); break;
    case 'mic_amplitude':     handleMicAmplitude(data.value); break;
    case 'wake_word_detected': handleWakeWordDetected(); break;
  }
}

// ---- Audio amplitude (Gemini speaking) → lip sync ----
function handleAudioAmplitude(value) {
  face.updateAudioAmplitude(value);
}

// ---- Mic amplitude (user speaking) → waveform ----
function handleMicAmplitude(value) {
  face.updateMicAmplitude(value);
}

// ---- Wake word flash ----
function handleWakeWordDetected() {
  face.wakeWordFlash();
  showBubble('🔔 ได้ยินครับ...', 1500);
  // Quick surprised → back to listening
  setEmotion('surprised');
  setTimeout(() => {
    if (appContainer.classList.contains('state-listening')) return;
    setEmotion('listening');
  }, 400);
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
  }, 4000);
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
  statusHint.innerText = `${seconds}s`;
}

let zzzInterval = null;

function startZzzAnimation() {
  const container = document.getElementById('sleep-zzz-container');
  if (!container) return;
  
  container.innerHTML = '';
  if (zzzInterval) clearInterval(zzzInterval);
  
  zzzInterval = setInterval(() => {
    const zzz = document.createElement('div');
    zzz.className = 'zzz-particle';
    
    // Spawn Zzz near the right eye area: X: ~58%-70%, Y: ~38%-46%
    const randomX = 58 + Math.random() * 12;
    const randomY = 38 + Math.random() * 8;
    
    zzz.style.left = `${randomX}%`;
    zzz.style.top = `${randomY}%`;
    
    const sizes = ['12px', '18px', '24px', '32px'];
    const size = sizes[Math.floor(Math.random() * sizes.length)];
    zzz.style.fontSize = size;
    
    const texts = ['z', 'Z', 'Zz', 'Zzz'];
    zzz.innerText = texts[Math.floor(Math.random() * texts.length)];
    
    const duration = 3.5 + Math.random() * 1.5;
    zzz.style.animationDuration = `${duration}s`;
    
    container.appendChild(zzz);
    
    setTimeout(() => {
      zzz.remove();
    }, duration * 1000);
  }, 1200);
}

function stopZzzAnimation() {
  if (zzzInterval) {
    clearInterval(zzzInterval);
    zzzInterval = null;
  }
  const container = document.getElementById('sleep-zzz-container');
  if (container) container.innerHTML = '';
}

function updateState(state) {
  stopZzzAnimation();
  appContainer.classList.remove('state-listening', 'state-thinking', 'state-speaking', 'state-sleepy');
  if (state !== 'idle') appContainer.classList.add(`state-${state}`);

  const pauseAiBtn = document.getElementById('pause-ai-btn');
  if (pauseAiBtn) {
    if (state === 'sleepy') {
      pauseAiBtn.classList.add('paused');
      pauseAiBtn.title = "เปิดใช้งาน AI";
    } else {
      pauseAiBtn.classList.remove('paused');
      pauseAiBtn.title = "พักการทำงาน AI";
    }
  }

  countdownArc.classList.remove('active');
  countdownArc.style.setProperty('--countdown-pct', '0%');

  clearThinkingTimer();

  // Reset amplitude tracking on state change
  face._lastAudioAmp = 0;
  face._lastMicAmp   = 0;

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
    // Reset ambient rings
    document.querySelectorAll('.ambient-ring').forEach(el => el.style.transform = '');
  } else if (state === 'speaking') {
    isPttPressed = false;
    statusHint.innerText = 'SPEAKING';
    hideBubble();
    setEmotion('speaking');
  } else if (state === 'sleepy') {
    isPttPressed = false;
    statusHint.innerText = 'PAUSED';
    setEmotion('sleepy');
    startZzzAnimation();
    document.querySelectorAll('.ambient-ring').forEach(el => el.style.transform = '');
  } else {
    isPttPressed = false;
    statusHint.innerText = 'READY';
    setEmotion('neutral');
    document.querySelectorAll('.ambient-ring').forEach(el => el.style.transform = '');
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
  if (state.includes('state-sleepy')) {
    // AI is paused/sleepy — do nothing
    return;
  }
  if (state.includes('state-thinking')) {
    // In thinking — tap to barge-in (interrupt) by sending ptt_press
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ptt_press' }));
    return;
  }
  if (state.includes('state-listening')) {
    // Tap again while listening = manually release (send now)
    releasePTT();
    return;
  }
  pressPTT();
}

// Tap face-stage to toggle talk
faceStage.addEventListener('click', (e) => { e.preventDefault(); toggleMic(); });
faceStage.addEventListener('touchend', (e) => { e.preventDefault(); toggleMic(); });

// Test Speaker
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

// Telemedicine Manual Button
const telemedManualBtn = document.getElementById('telemed-manual-btn');
if (telemedManualBtn) {
  telemedManualBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'trigger_telemedicine_manual' }));
    }
    // Open overlay immediately (don't wait for server echo)
    showTelemedicineCall('ผู้ป่วยขอพบแพทย์', 'https://hub-api.socare.app/videoCall?roomName=SocareTelemed');
  });
}

// Pause AI Button
const pauseAiBtn = document.getElementById('pause-ai-btn');
if (pauseAiBtn) {
  pauseAiBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (socket?.readyState === WebSocket.OPEN) {
      const isPaused = pauseAiBtn.classList.contains('paused');
      socket.send(JSON.stringify({ type: isPaused ? 'resume_ai' : 'pause_ai' }));
    }
  });
}


// ---- Cards ----
function renderContentCard(data) {
  if (data.card_type === 'id_card_clear') {
    const existingCard = cardsList.querySelector('.card-id_card');
    if (existingCard) {
      existingCard.remove();
    }
    if (cardsList.children.length === 0) {
      cardsList.innerHTML = '<div class="placeholder-card">ไม่มีการแจ้งเตือนในขณะนี้</div>';
    }
    return;
  }

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

  if (data.card_type === 'id_card') {
    const existingCard = cardsList.querySelector('.card-id_card');
    if (existingCard) {
      existingCard.remove();
    }
  }

  const card = document.createElement('div');
  card.className = `dynamic-card card-${data.card_type}`;
  card.style.position = 'relative';

  if (data.card_type === 'id_card' && data.payload) {
    try {
      const payloadObj = JSON.parse(data.payload);
      if (payloadObj.img) {
        const imgEl = document.createElement('img');
        imgEl.src = 'data:image/jpeg;base64,' + payloadObj.img;
        imgEl.style.cssText = 'width: 75px; height: 95px; border-radius: 8px; float: right; margin-left: 12px; border: 1.5px solid rgba(0, 212, 255, 0.4); object-fit: cover;';
        card.appendChild(imgEl);
      }
    } catch(e) {}
  }

  const h3 = document.createElement('h3'); h3.innerText = data.title;
  const p  = document.createElement('p');  p.innerText  = data.body;
  p.style.whiteSpace = 'pre-line'; // Ensure line breaks show correctly
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

// ---- Telemedicine (iframe → direct Jitsi URL) ----
const jitsiContainer = document.getElementById('jitsi-container');
let jitsiAPI = null;

function showTelemedicineCall(reason, url) {
  // หากหน้าต่างเปิดอยู่แล้ว ไม่ต้องโหลดใหม่เพื่อป้องกันการหลุดสาย
  if (telemedOverlay.style.display === 'flex') {
    return;
  }

  setEmotion('concerned');
  showBubble('🩺 กำลังต่อสายหาคุณหมอ... กรุณารอสักครู่', 4000);

  // เคลียร์ container
  jitsiContainer.innerHTML = '';

  const domain = "meet.socare.app";
  const options = {
      roomName: 'SocareTelemed',
      width: '100%',
      height: '100%',
      parentNode: jitsiContainer,
      userInfo: {
          displayName: 'ผู้ป่วย',
      },
      configOverwrite: {
          disableDeepLinking: true,
          prejoinPageEnabled: false,
          disableLocalVideoFlip: true,
          doNotFlipLocalVideo: true,
          hideParticipantsStats: true,
          disableRemoteMute: true,
          disableRemoteControl: true,
          hideConferenceTimer: false,
          remoteVideoMenu: {
              disableKick: true,
              disableGrantModerator: true,
          },
          subject: 'ต่อสายหาคุณหมอ',
          startWithAudioMuted: false,
          startWithVideoMuted: false,
          disableAGC: true
      },
      interfaceConfigOverwrite: {
          FILM_STRIP_MAX_HEIGHT: 0.1,
          SHOW_CHROME_EXTENSION_BANNER: false,
          DISABLE_DOMINANT_SPEAKER_INDICATOR: true,
          LANG_DETECTION: true,
          VIDEO_QUALITY_LABEL_DISABLED: true,
          CONNECTION_INDICATOR_DISABLED: true,
          TOOLBAR_BUTTONS: ['microphone', 'camera', 'fullscreen', 'tileview', 'desktop', 'profile', 'settings', 'chat', 'hangup']
      }
  };

  try {
      jitsiAPI = new JitsiMeetExternalAPI(domain, options);
      
      // ดักจับอีเวนต์การวางสายจากห้องสนทนาของ Jitsi
      jitsiAPI.addEventListener('readyToClose', () => {
          endTelemedicineCall();
      });
      jitsiAPI.addEventListener('videoConferenceLeft', () => {
          endTelemedicineCall();
      });
  } catch (err) {
      console.error("Failed to initialize Jitsi API:", err);
      jitsiContainer.innerHTML = `<div style="color:#f87171; text-align:center; padding:20px; font-family:Sarabun,sans-serif;">❌ ไม่สามารถโหลดระบบเชื่อมต่อสายได้</div>`;
  }

  telemedOverlay.style.display = 'flex';
}

function endTelemedicineCall() {
  if (jitsiAPI) {
    try {
      jitsiAPI.executeCommand('hangup');
      jitsiAPI.dispose();
    } catch (e) {
      console.error("Error disposing Jitsi:", e);
    }
    jitsiAPI = null;
  }
  jitsiContainer.innerHTML = '';
  telemedOverlay.style.display = 'none';
  setEmotion('neutral');
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'telemedicine_end' }));
  }
}

endTelemedBtn.addEventListener('click', () => endTelemedicineCall());



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
