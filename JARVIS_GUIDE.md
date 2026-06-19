# JARVIS Robot — คู่มือดูแลและแก้ปัญหา
> อัพเดทล่าสุด: 2026-06-19

---

## 📁 โครงสร้างโปรเจกต์

```
robot_home_use/
├── backend/
│   ├── main.py           # ตัวหลัก orchestrator, WebSocket server, state machine
│   ├── gemini_client.py  # เชื่อมต่อ Gemini Live API, auto-reconnect
│   ├── audio_handler.py  # จัดการไมค์ + ลำโพง (sounddevice)
│   ├── wake_word.py      # Wake word detector (Vosk) — ปลุก "จาวิส"
│   ├── db_manager.py     # SQLite สำหรับ vitals, reminders
│   ├── requirements.txt  # Python dependencies
│   └── models/
│       └── vosk-small-en/ # Vosk model (~40MB, download ครั้งเดียว)
├── frontend/
│   ├── index.html        # UI หน้าจอ
│   ├── style.css         # สไตล์ตาหุ่นยนต์ WALL-E
│   └── app.js            # Animation engine + WebSocket client
├── deploy.sh             # rsync Mac → Pi
└── .env                  # API keys (ไม่ commit ใน git!)
```

---

## 🚀 วิธี Start ระบบ

### บน Pi (ผ่าน SSH)
```bash
ssh devpi

# Kill process เก่า
kill $(cat /tmp/robot.pid 2>/dev/null) 2>/dev/null
fuser -k 8765/tcp 2>/dev/null
sleep 2

# Start backend
cd ~/Desktop/robot_home_use/backend
nohup ../.venv/bin/python -u main.py > /tmp/robot.log 2>&1 &
echo $! > /tmp/robot.pid
echo "Started PID: $(cat /tmp/robot.pid)"

# เปิด browser เต็มจอ
DISPLAY=:0 chromium-browser --start-fullscreen \
  --app='file:///home/socio/Desktop/robot_home_use/frontend/index.html' &
```

---

## 🔍 วิธีเช็คสถานะและ Error

### ดู Log แบบ realtime
```bash
ssh devpi "tail -f /tmp/robot.log"
```

### ดูเฉพาะ Events สำคัญ (PTT, State, Error)
```bash
ssh devpi "grep -E 'PTT|State|Error|Gemini|SPEAK|THINK|drop|reconnect' /tmp/robot.log | tail -30"
```

### เช็ค Gemini เชื่อมต่อหรือยัง
```bash
ssh devpi "grep -E '🟢|🔴' /tmp/robot.log | tail -5"
```

### เช็ค Vosk wake word พร้อมหรือยัง
```bash
ssh devpi "grep -E 'Vosk wake word ready|Failed to download' /tmp/robot.log"
```

### เช็ค process ที่ run อยู่
```bash
ssh devpi "ps aux | grep main.py | grep -v grep"
```

### เช็ค port 8765 ว่าง/ใช้งาน
```bash
ssh devpi "ss -tlnp | grep 8765"
```

### เช็ค DNS ของ Pi
```bash
ssh devpi "getent hosts generativelanguage.googleapis.com && echo OK || echo BROKEN"
```

---

## 🛠️ ปัญหาที่เจอบ่อย และวิธีแก้

### ❌ "Connection failed: [Errno -3] Temporary failure in name resolution"
**สาเหตุ:** DNS บน Pi ใช้งาน router ที่ไม่เสถียร

**แก้:**
```bash
ssh devpi "printf 'nameserver 8.8.8.8\nnameserver 8.8.4.4\n' | sudo tee /etc/resolv.conf"
```
> ⚠️ จะ reset หลัง reboot — ถ้าอยากถาวรต้องแก้ใน NetworkManager config

---

### ❌ "OSError: [Errno 98] address already in use"
**สาเหตุ:** process เก่ายังค้างอยู่บน port 8765

**แก้:**
```bash
ssh devpi "fuser -k 8765/tcp; sleep 2"
# หรือ kill ด้วย PID โดยตรง
ssh devpi "sudo kill -9 \$(cat /tmp/robot.pid)"
```

---

### ❌ "Gemini session dropped (1006)" หรือ "keepalive ping timeout"
**สาเหตุ:** Wi-Fi Pi latency สูง ทำให้ connection หลุด

**สิ่งที่ทำไปแล้ว:**
- ✅ Auto-reconnect loop — reconnect อัตโนมัติใน 3 วินาที
- ✅ Thinking timeout ขยายจาก 4.5s → 10s
- ✅ Receive loop break เมื่อเจอ 1006/1011 แทนที่จะ spam error

**ถ้ายังหลุดบ่อย:** ลองเสียบสาย LAN แทน Wi-Fi

---

### ❌ พูดแล้วไม่มีเสียงตอบ
**เช็คตามลำดับ:**

1. ดู log — มี `PTT Released` ไหม?
```bash
ssh devpi "grep PTT /tmp/robot.log | tail -10"
```

2. มี `State updated: THINKING` ไหม? (แปลว่า audio ถูกส่ง)
```bash
ssh devpi "grep -E 'THINK|SPEAK' /tmp/robot.log | tail -5"
```

3. Gemini ยัง connected อยู่ไหม?
```bash
ssh devpi "grep -E '🟢|🔴|reconnect' /tmp/robot.log | tail -5"
```

4. ถ้า session หลุด — รอ auto-reconnect 3 วิ แล้วลองใหม่

---

### ❌ หน้าจอดับ (screensaver)
**แก้ครั้งเดียว:**
```bash
ssh devpi "
xset -display :0 s off
xset -display :0 -dpms
xset -display :0 s noblank
"
```
**ถาวร (ใส่ใน autostart แล้ว):** `~/.config/lxsession/LXDE-pi/autostart`

---

## 🔄 วิธี Deploy โค้ดใหม่จาก Mac ไปยัง Pi

```bash
cd /Users/rkdkmac15/Documents/robot_home_use
bash deploy.sh
```

แล้ว restart backend:
```bash
ssh devpi "kill \$(cat /tmp/robot.pid); sleep 2; cd ~/Desktop/robot_home_use/backend && nohup ../.venv/bin/python -u main.py > /tmp/robot.log 2>&1 & echo \$! > /tmp/robot.pid"
```

---

## 🎙️ Wake Word "จาวิส"

**ใช้:** Vosk (open source, ไม่ต้องสมัคร account)
- Model: `backend/models/vosk-small-en/` (~40MB, English)
- ตรวจจับ: "jarvis", "hi jarvis", "hello jarvis" (รวม "จาวิส" เพราะเสียงใกล้เคียง)
- ถ้า Vosk ไม่พร้อม → ใช้ปุ่ม PTT บนหน้าจอได้ตามปกติ

**เช็คว่า Vosk พร้อมหรือยัง:**
```bash
ssh devpi "grep 'Vosk wake word ready' /tmp/robot.log"
```

---

## 🤖 States ของหุ่นยนต์

| State | ตาสี | หมายความ |
|---|---|---|
| STANDBY | 🔵 น้ำเงิน | รอคำสั่ง กะพริบตา มองรอบๆ |
| LISTENING | 🩵 ฟ้าสด | รับฟังเสียงอยู่ ตาเบิกกว้าง |
| THINKING | 🟣 ม่วง | กำลังประมวลผล ตามองขึ้นซ้าย |
| SPEAKING | 🟢 เขียว | กำลังพูดตอบ ตาเต้น rhythm |
| HAPPY | 🟡 เหลือง | ยิ้ม ตาโค้ง |
| CONCERNED | 🔴 แดง | กังวล เช่น vitals ผิดปกติ |
| OFFLINE | ⬛ เทา | WebSocket หลุด |

---

## 📋 Dependencies บน Pi

```bash
# Install หากหาย
cd ~/Desktop/robot_home_use
.venv/bin/pip install google-genai websockets python-dotenv numpy sounddevice soundfile vosk

# ตรวจสอบ
.venv/bin/pip list | grep -E 'genai|vosk|sounddevice'
```

---

## 🔑 Environment Variables (.env)

```env
GEMINI_API_KEY=<your_key>      # จาก Google AI Studio
GEMINI_MODEL=gemini-2.5-flash-native-audio-latest
PORT=8765
MIC_DIGITAL_GAIN=1.0           # ปรับ gain ไมค์ (1.0 = ปกติ, 2.0 = เพิ่ม 2 เท่า)
```

---

## 🌐 Pi SSH Config

```
Host devpi
    HostName 192.168.1.53
    User socio
    IdentityFile ~/.ssh/id_ed25519_buzz
```
