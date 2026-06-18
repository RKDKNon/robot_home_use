# Software Requirements Specification (SRS)
## Health Robot — AI ผู้ช่วยดูแลสุขภาพ

| | |
|---|---|
| **เวอร์ชัน** | 0.1 (Draft) |
| **วันที่** | 2026-06-18 |
| **สถานะ** | ร่างเพื่อส่งต่อทีม Dev |
| **ผู้จัดทำ** | (ทีมผลิตภัณฑ์) |

---

## 1. บทนำ (Introduction)

### 1.1 วัตถุประสงค์
เอกสารนี้ระบุความต้องการของระบบ **Health Robot** หุ่นยนต์ผู้ช่วยดูแลสุขภาพแบบตั้งโต๊ะ ที่สนทนาด้วยเสียง แสดงอารมณ์บนหน้าจอ วิเคราะห์ภาพ วัดสัญญาณชีพ เตือนกินยา และเชื่อมต่อ telemedicine ผ่านระบบ Socare

### 1.2 ขอบเขต (Scope)
- **In scope:** การสนทนาเสียงสองทาง, ใบหน้าแสดงอารมณ์, wake word + push-to-talk, reminder, คำปรึกษาสุขภาพเบื้องต้น, AI vision, การอ่านค่า vital sign ผ่าน Bluetooth, การเชื่อมต่อ Socare
- **Out of scope (เบื้องต้น):** การวินิจฉัยโรค/สั่งยา, การเคลื่อนที่ (mobility), multi-language เต็มรูปแบบ (เริ่มที่ภาษาไทย)

### 1.3 กลุ่มเป้าหมายผู้ใช้
- **Primary:** ผู้สูงอายุ / ผู้ป่วยที่ดูแลตัวเองที่บ้าน
- **Secondary:** ผู้ดูแล (caregiver), บุคลากรทางการแพทย์ผ่าน Socare

### 1.4 คำนิยามและตัวย่อ
| คำ | ความหมาย |
|---|---|
| Wake Word | คำปลุกที่ตรวจจับแบบ local เพื่อเปิด session |
| PTT | Push-to-talk ปุ่มกดเพื่อพูด |
| VAD | Voice Activity Detection ตรวจจับว่ามีคนพูดอยู่ |
| Vital Sign | สัญญาณชีพ (ความดัน, ชีพจร, SpO2, อุณหภูมิ, น้ำตาล ฯลฯ) |
| Live API | Gemini Live API (streaming เสียง+วิดีโอ เรียลไทม์) |
| Tool / Function Call | กลไกที่ให้ AI สั่งงานระบบ (เปลี่ยนอารมณ์, ตั้งเตือน ฯลฯ) |

---

## 2. ภาพรวมระบบ (System Overview)

### 2.1 สถาปัตยกรรม
```
┌─────────────────────────── Raspberry Pi 4 (>=4GB) ────────────────────────┐
│                                                                            │
│  [Webcam+Mic] ─┐                                ┌─ [LCD 7" / Browser UI]   │
│  [Speaker] ◀───┤                                │   ใบหน้า + อารมณ์ + content│
│  [BT Vital] ───┤      Python Orchestrator       │                          │
│                │   ┌─────────────────────────┐  │                          │
│                ├──▶│ Audio I/O (AEC/VAD)      │  │                          │
│                │   │ Wake Word Engine (local) │  │── WebSocket (localhost) ─┘│
│                │   │ Gemini Session Manager   │  │                          │
│                │   │ Tool Dispatcher          │  │                          │
│                │   │ Reminder Scheduler       │  │                          │
│                │   │ BLE Manager              │  │                          │
│                │   │ Socare Connector         │  │                          │
│                │   │ Emergency Detector (opt) │  │                          │
│                │   └─────────────────────────┘  │                          │
└────────────────────────────┬───────────────────────────────────────────────┘
                            │ (internet)
            ┌────────────────┼─────────────────┬──────────────┐
        Gemini Live API   Socare API      Local Store    (Cloud backup?)
        (เสียง+vision)    (telemedicine)   (SQLite)
```

### 2.2 หลักการออกแบบ
1. **Local-first สำหรับงานวิกฤต** — reminder และการแจ้งเตือน vital sign ผิดปกติต้องทำงานได้แม้เน็ตหลุด
2. **AI ควบคุมผ่าน Function Calling** — ทุกการกระทำ (เปลี่ยนอารมณ์, แสดง content, ตั้งเตือน, อ่านค่า, เปิด telemedicine) เป็น tool ที่ model เรียก
3. **Browser เป็น display layer เท่านั้น** — รับคำสั่งผ่าน WebSocket ไม่ถือ business logic
4. **Privacy by design** — เสียงที่ไม่ใช่คำปลุกไม่ออกจากเครื่อง

---

## 3. ความต้องการเชิงฟังก์ชัน (Functional Requirements)

### FR-1 Wake Word & การเริ่มสนทนา
- **FR-1.1** ระบบต้องฟังคำปลุกแบบ local/offline ตลอดเวลา โดยไม่ส่งเสียงขึ้น cloud จนกว่าจะตรวจพบคำปลุก
- **FR-1.2** เมื่อตรวจพบคำปลุก ต้องเปิด Gemini Live session ภายใน < 1 วินาที และแสดง feedback (ใบหน้าเปลี่ยนเป็น "listening" + เสียง/ภาพตอบรับ)
- **FR-1.3** ต้องมี **Push-to-talk (PTT)** เป็นทางเลือกสำรอง: กดปุ่ม (ฮาร์ดแวร์หรือ touch บนจอ) เพื่อเริ่มสนทนาโดยไม่ต้องพูดคำปลุก
- **FR-1.4** เมื่อเงียบเกิน N วินาที (ค่าเริ่มต้น 8–10 วินาที, ปรับได้) ให้ปิด session แล้วกลับสู่สถานะ idle
- **FR-1.5** เสียงที่ไม่ตรงคำปลุกต้องถูกทิ้งทันทีในหน่วยความจำ ไม่บันทึก ไม่ส่งออกนอกเครื่อง
- **FR-1.6** คำปลุกต้องกำหนด/เปลี่ยนได้ผ่านการตั้งค่า (ค่าเริ่มต้น TBD — ต้องเลือกคำภาษาไทย)

### FR-2 การสนทนาด้วยเสียง (Voice Conversation)
- **FR-2.1** สนทนาสองทางแบบเรียลไทม์ผ่าน Gemini Live API ภาษาไทย
- **FR-2.2** ต้องมี Acoustic Echo Cancellation (AEC) เพื่อไม่ให้ robot ได้ยินเสียงตัวเองจากลำโพง
- **FR-2.3** ต้องรองรับการขัดจังหวะ (barge-in) — ผู้ใช้พูดแทรกขณะ robot กำลังพูดได้
- **FR-2.4** สถานะการสนทนาต้องสะท้อนบนใบหน้า: idle → listening → thinking → speaking

### FR-3 ใบหน้าและการแสดงผล (Face & Display)
- **FR-3.1** แสดงใบหน้า animation บนจอ LCD 7" พร้อมชุดอารมณ์พื้นฐาน (เช่น neutral, happy, concerned, sad, surprised, sleepy) — รายการสุดท้าย TBD
- **FR-3.2** AI ต้องสั่งเปลี่ยนอารมณ์ได้ผ่าน function call เช่น `set_emotion(emotion, intensity)`
- **FR-3.3** AI ต้องสั่งแสดง content เสริมบนจอได้ผ่าน function call เช่น `show_content(type, payload)` โดยรองรับอย่างน้อย: ข้อความ, รูปภาพ, ค่า vital sign, การ์ด reminder (ประเภทอื่นๆ TBD)
- **FR-3.4** ขณะ idle ใบหน้าต้องแสดงสถานะพักที่ดูเป็นธรรมชาติ (เช่น หลับตา/มองรอบๆ) และมี indicator เมื่อออฟไลน์

### FR-4 Reminder (การแจ้งเตือน)
- **FR-4.1** สร้าง/แก้ไข/ลบ reminder ได้ด้วยเสียง (ผ่าน AI function call) และทำงานแบบ local
- **FR-4.2** Reminder ต้องทำงานได้แม้ออฟไลน์ (เก็บใน local store เช่น SQLite)
- **FR-4.3** เมื่อถึงเวลา ต้องแจ้งเตือนด้วยเสียง + ใบหน้า + การ์ดบนจอ
- **FR-4.4** ต้องรองรับการ "รับทราบ" (acknowledge) และแจ้งซ้ำ (snooze/repeat) หากผู้ใช้ไม่ตอบรับภายในเวลาที่กำหนด
- **FR-4.5** รองรับ reminder ประเภทกินยา พร้อมข้อมูลชื่อยา/ขนาด/เวลา

### FR-5 คำปรึกษาสุขภาพเบื้องต้น (Health Guidance)
- **FR-5.1** ตอบคำถามสุขภาพทั่วไปและให้คำแนะนำเบื้องต้นได้ตามขอบเขตที่กำหนด
- **FR-5.2** **ต้องไม่** วินิจฉัยโรคหรือสั่ง/ปรับยา — ต้องมี guardrail บังคับ
- **FR-5.3** ต้องแสดง disclaimer ว่าไม่ใช่คำวินิจฉัยทางการแพทย์ และแนะนำพบแพทย์เมื่อเหมาะสม
- **FR-5.4** ต้องมี logic escalation: เมื่อพบสัญญาณอันตราย (จากบทสนทนาหรือค่า vital sign) ให้แนะนำ/เชื่อมต่อช่องทางฉุกเฉินหรือ Socare
- **FR-5.5** สนทนาเรื่องทั่วไป (non-health) ได้ตามความเหมาะสม

### FR-6 AI Vision
- **FR-6.1** วิเคราะห์ภาพจากกล้องได้แบบ on-demand (ผู้ใช้สั่ง เช่น "ดูนี่ให้หน่อย")
- **FR-6.2** ส่ง frame ไป Gemini เฉพาะเมื่อจำเป็น (ไม่ stream ต่อเนื่องโดยไม่ได้สั่ง) เพื่อควบคุม cost และ privacy
- **FR-6.3** ต้องมี indicator ชัดเจนเมื่อกล้องกำลังทำงาน (privacy)
- **FR-6.4** กรณีการใช้งานเริ่มต้น: อ่านฉลากยา, ดูวัตถุ/สิ่งของ, ประเมินสภาพแวดล้อมเบื้องต้น (รายการสุดท้าย TBD)

### FR-7 Vital Sign ผ่าน Bluetooth
- **FR-7.1** เชื่อมต่อและอ่านค่าจากอุปกรณ์วัด vital sign ผ่าน BLE
- **FR-7.2** รองรับรายการอุปกรณ์ที่ระบุชัดเจน (รุ่น/ยี่ห้อ — **TBD, ต้องล็อกก่อนเริ่ม dev**)
- **FR-7.3** แสดงค่าที่อ่านได้บนจอ + บันทึกลง local store
- **FR-7.4** เมื่อค่าผิดปกติเกินเกณฑ์ ต้องแจ้งเตือนและกระตุ้น escalation (ดู FR-5.4) ไม่ใช่แค่เล่าค่า
- **FR-7.5** AI เข้าถึงค่าล่าสุดได้ผ่าน function call เช่น `get_vitals()` เพื่อใช้ประกอบคำแนะนำ

### FR-8 Telemedicine (Socare)
- **FR-8.1** เริ่ม/เข้าร่วม video consultation ผ่านระบบ Socare ได้
- **FR-8.2** รายละเอียด API/SDK/flow การ auth ผู้ป่วย — **TBD, รอ spec จากทีม Socare**
- **FR-8.3** ต้องผูกตัวตนผู้ป่วยและส่งข้อมูลที่จำเป็น (เช่น vital sign ล่าสุด) ตามที่ Socare รองรับและภายใต้ consent

### FR-9 Emergency Keyword Detection (Optional)
- **FR-9.1** ตรวจจับคำขอความช่วยเหลือ (เช่น "ช่วยด้วย") แบบ local ได้ตลอดเวลาแม้ไม่ได้ปลุก
- **FR-9.2** เมื่อตรวจพบ ต้องยืนยันกับผู้ใช้ก่อนดำเนินการ (กัน false positive) แล้วจึงกระตุ้น escalation/แจ้งผู้ดูแล/เชื่อม Socare
- **FR-9.3** ต้องปรับ sensitivity และเปิด/ปิดได้ พร้อมประเมิน false-accept/false-reject ใน PoC
- **FR-9.4** ต้องสื่อสารกับผู้ใช้ว่ามีการฟังคำฉุกเฉินตลอดเวลา (ความโปร่งใส/consent)

---

## 4. ความต้องการที่ไม่ใช่ฟังก์ชัน (Non-Functional Requirements)

### NFR-1 ประสิทธิภาพ (Performance)
- **NFR-1.1** Latency เสียงไป-กลับ (end-to-end) เป้าหมาย < 1.5 วินาทีบนเน็ตปกติ
- **NFR-1.2** Animation ใบหน้า >= 24 FPS บน Pi 4
- **NFR-1.3** Wake word เปิด session ภายใน < 1 วินาที
- **NFR-1.4** ต้องผ่าน thermal test — ไม่ throttle ภายใต้การใช้งานต่อเนื่อง (ต้องมี heatsink/fan)

### NFR-2 ความเสถียร & การทำงานออฟไลน์
- **NFR-2.1** เมื่อเน็ตหลุด ระบบต้องไม่ crash — แสดงสถานะออฟไลน์ และ reminder/แจ้งเตือนวิกฤตยังทำงาน
- **NFR-2.2** กู้คืน session อัตโนมัติเมื่อเน็ตกลับมา

### NFR-3 ความปลอดภัยข้อมูล & PDPA
- **NFR-3.1** ข้อมูลสุขภาพ/เสียง/ภาพถือเป็นข้อมูลอ่อนไหวสูงสุด — ต้องเข้ารหัสทั้ง at-rest และ in-transit
- **NFR-3.2** ต้องมี consent flow ก่อนใช้งานครั้งแรก และนโยบายการเก็บ/ลบข้อมูล
- **NFR-3.3** ต้องตรวจสอบและกำหนดค่าให้ Gemini API **ไม่นำข้อมูลผู้ใช้ไปเทรน** (พิจารณา Vertex AI / enterprise tier)
- **NFR-3.4** Indicator ชัดเจนเมื่อไมค์/กล้องทำงาน

### NFR-4 ความปลอดภัยทางการแพทย์ & กฎหมาย
- **NFR-4.1** Guardrail บังคับขอบเขต (ไม่วินิจฉัย/ไม่สั่งยา) ต้องทดสอบด้วยชุด adversarial prompt
- **NFR-4.2** ต้องมี disclaimer และเส้นทาง escalation ที่ชัดเจน
- **NFR-4.3** ทบทวนความรับผิด (liability) และข้อกำหนดเครื่องมือแพทย์กับฝ่ายกฎหมาย

### NFR-5 ต้นทุน (Cost)
- **NFR-5.1** ต้องประมาณการต้นทุน Gemini Live API ต่อเครื่องต่อวัน (ชั่วโมงใช้งาน × ราคา) และยืนยันกับโมเดลธุรกิจ
- **NFR-5.2** Wake word + on-demand vision ต้องช่วยลด cost โดยไม่เปิด session/ส่ง frame เกินจำเป็น

### NFR-6 การใช้งาน (Usability)
- **NFR-6.1** ออกแบบสำหรับผู้สูงอายุ — ตัวอักษร/ปุ่มใหญ่ชัด, เสียงดังพอ, ขั้นตอนน้อย
- **NFR-6.2** PTT ต้องเข้าถึงง่ายสำหรับผู้ที่ออกเสียงคำปลุกไม่ชัด

### NFR-7 การดูแลรักษา (Maintainability/Observability)
- **NFR-7.1** มี logging และ telemetry ตั้งแต่เริ่ม เพื่อ debug บน embedded device
- **NFR-7.2** อัปเดต OTA / remote config (พิจารณา)

---

## 5. ข้อกำหนดฮาร์ดแวร์ (Hardware Requirements)
| รายการ | สเปก |
|---|---|
| Mainboard | Raspberry Pi 4 (แนะนำ RAM >= 4GB) |
| จอแสดงผล | LCD 7" (touch — เพื่อรองรับ PTT/UI) |
| กล้อง | Webcam พร้อมไมค์ในตัว |
| เสียงออก | ลำโพง |
| Vital Sign | อุปกรณ์ BLE (รุ่น TBD) |
| ระบายความร้อน | Heatsink + fan (จาก NFR-1.4) |
| เครือข่าย | Wi-Fi (พิจารณา fallback) |

---

## 6. เทคโนโลยี (Technology Stack)
- **Backend/Orchestrator:** Python
- **AI:** Gemini Live API (เสียง + vision + function calling)
- **UI ใบหน้า:** Web (Browser) + WebSocket; แนะนำ animation แบบเบา (CSS/Canvas/Lottie)
- **Wake Word Engine:** ตัวเลือก openWakeWord / Picovoice Porcupine / Vosk — **ต้องเลือกใน Phase 0** (เกณฑ์: แม่นยำคำไทย, รันบน Pi, license)
- **Local Store:** SQLite
- **BLE:** BlueZ / Python BLE library

---

## 7. การตัดสินใจที่ค้างอยู่ (Open Issues / TBD)
| # | ประเด็น | ผู้รับผิดชอบ |
|---|---|---|
| O-1 | คำปลุกภาษาไทย (คำว่าอะไร) | Product |
| O-2 | เลือก Wake Word Engine | Dev (Phase 0) |
| O-3 | รายการรุ่น/ยี่ห้ออุปกรณ์ vital sign ที่รองรับ | Product + Procurement |
| O-4 | Spec API ของ Socare (REST/WebRTC, auth, data) | ทีม Socare |
| O-5 | ชุดอารมณ์ใบหน้าและประเภท content ที่รองรับ | Product + Design |
| O-6 | นโยบาย data retention + tier ของ Gemini (PDPA) | Legal + Dev |
| O-7 | ขอบเขตคำปรึกษาสุขภาพ + เกณฑ์ค่า vital sign ผิดปกติ | ที่ปรึกษาแพทย์ |
| O-8 | คำ/วิธีตรวจจับฉุกเฉิน + sensitivity | Dev (Phase 0) |
| O-9 | ประมาณการ cost Gemini ต่อเครื่อง/วัน | Dev + Finance |

---

## 8. แผนการพัฒนาแบบเฟส (Phased Roadmap)
- **Phase 0 — Spike/PoC (Go/No-Go):** Gemini Live + เสียงไทย + ใบหน้าพื้นฐาน + wake word บน Pi 4 จริง → วัด latency, FPS, ความร้อน, AEC, false-accept/reject ของ wake word & emergency keyword
- **Phase 1 — Core:** สนทนาเสียง + ใบหน้าอารมณ์ + wake word/PTT + reminder (local)
- **Phase 2 — Health & Vision:** AI vision + คำปรึกษาสุขภาพ + guardrails/disclaimer + escalation
- **Phase 3 — Vital Sign:** BLE integration (อุปกรณ์ที่ล็อกแล้ว) + แจ้งเตือนค่าผิดปกติ
- **Phase 4 — Telemedicine:** Socare integration
- **Optional/ขนานไปตลอด:** Emergency keyword detection, PDPA/consent/security hardening, observability

---

## 9. เกณฑ์การยอมรับ (Acceptance Criteria) — ระดับสูง
- ผู้ใช้เรียกด้วยคำปลุกหรือ PTT แล้วสนทนาภาษาไทยได้ลื่นไหล (latency ตามเป้า)
- ใบหน้าเปลี่ยนอารมณ์/แสดง content ตามคำสั่ง AI ได้ถูกต้อง
- ตั้งและรับการแจ้งเตือนกินยาได้ รวมถึงตอนออฟไลน์
- อ่านค่า vital sign จากอุปกรณ์ที่รองรับและแจ้งเตือนเมื่อผิดปกติ
- AI ปฏิเสธการวินิจฉัย/สั่งยา และ escalate เมื่อพบสัญญาณอันตราย
- เริ่ม telemedicine ผ่าน Socare ได้
- ผ่าน thermal และ offline-resilience test
