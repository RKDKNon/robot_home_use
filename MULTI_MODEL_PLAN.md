# Multi-Model AI Flow — JARVIS Robot

## Architecture Overview

```
ผู้ป่วยพูด → [Gemini Live API] ←→ เสียง (STT/TTS)
                    │
                    ├── function call: think_deeply → [mimo-v2.5-pro] (reasoning)
                    ├── function call: look_at_patient → [Gemini Vision] (กล้อง)
                    └── function call: look_at_object → [Gemini Vision] (ยา/สิ่งของ)
                    
                    ผลลัพธ์ → inject กลับ Gemini Live session → พูดตอบ
```

## Model Roles

| Model | หน้าที่ | ใช้เมื่อ |
|-------|---------|---------|
| **Gemini 2.5 Flash Native Audio** | สนทนาเสียงเรียลไทม์ + function calling | ตลอดเวลา (voice interface) |
| **mimo-v2.5-pro** | คิดซับซ้อน วิเคราะห์สุขภาพ ให้คำแนะนำเชิงลึก | ผู้ป่วยถามคำถามยาก / ต้องการการวิเคราะห์ |
| **Gemini 2.5 Flash (Vision)** | วิเคราะห์ภาพจากกล้อง | ดูหน้าผู้ป่วย / ดูยา |

## New Files

| ไฟล์ | หน้าที่ |
|------|---------|
| `backend/reasoning_client.py` | เชื่อมต่อ mimo-v2.5-pro ผ่าน Anthropic-compatible API |
| `backend/camera_handler.py` | จับภาพจาก webcam, encode เป็น base64 |

## New Tools (Function Calling)

| Tool | Model | คำอธิบาย |
|------|-------|---------|
| `think_deeply` | mimo-v2.5-pro | ส่งคำถามซับซ้อนไปคิดเชิงลึก |
| `look_at_patient` | Gemini Vision | จับภาพผู้ป่วย → วิเคราะห์สีหน้า/ท่าทาง |
| `look_at_object` | Gemini Vision | จับภาพสิ่งของ → 识别 ยา/อุปกรณ์ |

## Flow Examples

### Flow 1: ผู้ป่วยถามคำถามซับซ้อน
```
ผู้ป่วย: "ยาพาราเซตามอลกินพร้อมยาความดันได้ไหม"
Gemini Live: ได้ยิน → ตัดสินว่าต้องคิดลึก → เรียก think_deeply
mimo-v2.5-pro: วิเคราะห์ → "ไม่แนะนำให้กินพร้อมกัน เพราะ..."
Gemini Live: ได้ผลลัพธ์ → พูดตอบผู้ป่วย
```

### Flow 2: ดูหน้าผู้ป่วย
```
Gemini Live: เรียก look_at_patient
camera_handler: จับภาพ → base64
Gemini Vision: วิเคราะห์ → "ผู้ป่วยดูเหนื่อย มีสีหน้ากังวล"
Gemini Live: ได้ผลลัพธ์ → "คุณยายดูเหนื่อยนะคะ พักผ่อนนะคะ"
```

### Flow 3: ดูยา
```
ผู้ป่วย: "ยานี้คือยาอะไร"
Gemini Live: เรียก look_at_object
camera_handler: จับภาพ → base64
Gemini Vision: 识别 → "นี่คือ Paracetamol 500mg"
Gemini Live: "นี่คือยาพาราเซตามอล 500 มิลลิกรัมค่ะ"
```

## Environment Variables (.env)

```
# Existing
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash-native-audio-latest

# New - mimo reasoning
REASONING_API_URL=https://token-plan-sgp.xiaomimimo.com/anthropic
REASONING_API_KEY=...
REASONING_MODEL=mimo-v2.5-pro

# New - Camera
CAMERA_DEVICE=0
```

## Implementation Steps

1. ✅ `camera_handler.py` — จับภาพ webcam
2. ✅ `reasoning_client.py` — เชื่อมต่อ mimo-v2.5-pro
3. ✅ เพิ่ม tools: think_deeply, look_at_patient, look_at_object
4. ✅ อัพเดท gemini_client.py — เพิ่ม tool declarations
5. ✅ อัพเดท main.py — เพิ่ม tool handlers
6. ✅ Deploy + test
