# Robot Home Use

Project for robot home use automation and control.

---

## การตั้งค่าหน้าจอ DSI (Orange Pi CM4)

หากต่อจอผ่านสายแพ DSI แล้วจอไม่ติด/ทัชสกรีนใช้งานไม่ได้บนบอร์ด Orange Pi CM4 ให้ทำตามขั้นตอนการแก้ไขนี้ครับ:

### 1. สาเหตุของปัญหา
* คอนฟิกหน้าจอเดิม (`rpi7-overlay` หรือ `raspi-7inch-touchscreen-dsi0`) พยายามค้นหาชิปควบคุมจอและทัชสกรีนบนพอร์ต I2C-2 หรือ I2C-3 ซึ่งไม่ถูกต้องสำหรับบอร์ดตัวนี้
* จากการตรวจสอบจริง (สแกนพอร์ต) พบชิปคุมทัชสกรีน (`0x38`) และชิปจอ (`0x45`) ต่ออยู่บนพอร์ต **I2C-1** และจับคู่กับพอร์ตจอ **DSI1**

### 2. วิธีแก้ไข
1. แก้ไขไฟล์คอนฟิกบูตบนบอร์ด Orange Pi CM4:
   ```bash
   sudo nano /boot/orangepiEnv.txt
   ```
2. แก้ไขในส่วน `overlays=` ให้ใช้งาน `raspi-7inch-touchscreen` (ตัวนี้จะทำแผนผัง DSI1 + I2C-1 ให้ระบบตรวจหาจอและทัชสกรีนสำเร็จ):
   ```text
   overlays=i2c2-m1 i2c3-m0 i2c4-m0 raspi-7inch-touchscreen
   ```
3. บันทึกไฟล์แล้วรีบูตเครื่อง:
   ```bash
   sudo reboot
   ```

### 3. การตรวจสอบผลหลังแก้ไข
* **การเช็คระบบจอภาพ (DSI Link):**
  ```bash
  dmesg | grep -i dsi
  ```
  ควรพบ Log แจ้งว่าเปิดทำงานเสร็จสมบูรณ์:
  `final DSI-Link bandwidth: 696 x 1 Mbps`
  
* **การเช็คระบบทัชสกรีน (Touch Input):**
  ```bash
  cat /proc/bus/input/devices
  ```
  ควรพบอุปกรณ์อินพุตชื่อ `"fts_ts"` (Focaltech Touch Screen) ที่จับคู่อยู่บน handler `event1` พร้อมทำงาน
