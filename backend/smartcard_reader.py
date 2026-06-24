import asyncio
import random
import os
import sys
import base64
import re
import threading

# Guard to check if pyscard is installed
try:
    from smartcard.System import readers
    from smartcard.util import toBytes
    from smartcard.CardMonitoring import CardMonitor, CardObserver
    PYSCARD_AVAILABLE = True
except ImportError:
    PYSCARD_AVAILABLE = False

if PYSCARD_AVAILABLE:
    class KioskCardObserver(CardObserver):
        def __init__(self, service, loop):
            self.service = service
            self.loop = loop

        def update(self, observable, actions):
            (addedcards, removedcards) = actions
            for card in addedcards:
                self.loop.call_soon_threadsafe(
                    lambda c=card: asyncio.create_task(self.service.handle_card_added(c))
                )
            for card in removedcards:
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.service.handle_card_removed())
                )
else:
    class KioskCardObserver:
        def __init__(self, service, loop):
            pass

# Thai Citizen Card Constants & APDUs
SELECT = [0x00, 0xA4, 0x04, 0x00, 0x08]
THAI_CARD = [0xA0, 0x00, 0x00, 0x00, 0x54, 0x48, 0x00, 0x01]

CMD_CID = [0x80, 0xb0, 0x00, 0x04, 0x02, 0x00, 0x0d]
CMD_THFULLNAME = [0x80, 0xb0, 0x00, 0x11, 0x02, 0x00, 0x64]
CMD_ENFULLNAME = [0x80, 0xb0, 0x00, 0x75, 0x02, 0x00, 0x64]
CMD_BIRTH = [0x80, 0xb0, 0x00, 0xD9, 0x02, 0x00, 0x08]
CMD_GENDER = [0x80, 0xb0, 0x00, 0xE1, 0x02, 0x00, 0x01]
CMD_ISSUER = [0x80, 0xb0, 0x00, 0xF6, 0x02, 0x00, 0x64]
CMD_ISSUE = [0x80, 0xb0, 0x01, 0x67, 0x02, 0x00, 0x08]
CMD_EXPIRE = [0x80, 0xb0, 0x01, 0x6F, 0x02, 0x00, 0x08]
CMD_ADDRESS = [0x80, 0xb0, 0x15, 0x79, 0x02, 0x00, 0x64]

PHOTO_CMDS = [
    [0x80, 0xb0, 0x01, 0x7B, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x02, 0x7A, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x03, 0x79, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x04, 0x78, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x05, 0x77, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x06, 0x76, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x07, 0x75, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x08, 0x74, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x09, 0x73, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x0A, 0x72, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x0B, 0x71, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x0C, 0x70, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x0D, 0x6F, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x0E, 0x6E, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x0F, 0x6D, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x10, 0x6C, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x11, 0x6B, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x12, 0x6A, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x13, 0x69, 0x02, 0x00, 0xFF],
    [0x80, 0xb0, 0x14, 0x68, 0x02, 0x00, 0xFF],
]

def reset_usb_reader():
    """Soft reset USB reader port for AU9540 reader."""
    import glob
    import fcntl
    
    TARGET_VENDOR = "058f"
    TARGET_PRODUCT = "9540"
    USBDEVFS_RESET = ord('U') << 8 | 20
    
    print("💳 [SmartCard] [USB Reset] Searching for Alcor Micro AU9540 smartcard reader...")
    for path in glob.glob("/sys/bus/usb/devices/*"):
        try:
            vendor_file = os.path.join(path, "idVendor")
            product_file = os.path.join(path, "idProduct")
            
            if os.path.exists(vendor_file) and os.path.exists(product_file):
                with open(vendor_file, "r") as f:
                    vendor = f.read().strip()
                with open(product_file, "r") as f:
                    product = f.read().strip()
                    
                if vendor.lower() == TARGET_VENDOR.lower() and product.lower() == TARGET_PRODUCT.lower():
                    bus_file = os.path.join(path, "busnum")
                    dev_file = os.path.join(path, "devnum")
                    if os.path.exists(bus_file) and os.path.exists(dev_file):
                        with open(bus_file, "r") as f:
                            bus = int(f.read().strip())
                        with open(dev_file, "r") as f:
                            dev = int(f.read().strip())
                            
                        dev_path = f"/dev/bus/usb/{bus:03d}/{dev:03d}"
                        print(f"💳 [SmartCard] [USB Reset] Found USB reader device at {dev_path}. Sending USBDEVFS_RESET...")
                        
                        with open(dev_path, "wb") as fd:
                            fcntl.ioctl(fd, USBDEVFS_RESET, 0)
                            
                        print("💳 [SmartCard] [USB Reset] USBDEVFS_RESET sent successfully.")
                        return True
        except Exception as e:
            print(f"💳 [SmartCard] [USB Reset] Error resetting USB reader at {path}: {e}")
            
    print("💳 [SmartCard] [USB Reset] Alcor Micro AU9540 smartcard reader USB device not found.")
    return False

class SmartCardReaderService:
    def __init__(self, state_manager):
        self.state_manager = state_manager
        self.is_running = False
        self.card_present = False
        self.task = None
        self.reader_name = None

    def thai2unicode(self, data):
        """Decode TIS-620 encoded byte lists to clean string."""
        if isinstance(data, list):
            try:
                resp = bytes(data).decode('tis-620').replace('#', ' ')
                return resp.strip()
            except Exception:
                return ""
        return data

    def parse_address(self, addr):
        """Parses elements out of a raw Thai ID card address string."""
        result = {"raw": addr}
        m = re.search(r'(\S+)\s+หมู่ที่\s*(\d+)', addr)
        if m:
            result["house_no"] = m.group(1)
            result["moo"] = m.group(2)
        m = re.search(r'ถนน\s*(\S+)', addr)
        if m:
            result["road"] = m.group(1)
        m = re.search(r'ตำบล\s*(\S+)', addr)
        if m:
            result["tambon"] = m.group(1)
        m = re.search(r'อำเภอ\s*(\S+)', addr)
        if m:
            result["amphoe"] = m.group(1)
        m = re.search(r'จังหวัด\s*(\S+)', addr)
        if m:
            result["province"] = m.group(1)
        return result

    async def read_card_data(self, connection, atr):
        loop = asyncio.get_running_loop()
        
        def blocking_read():
            # 1. Select Applet
            _, sw1, sw2 = connection.transmit(SELECT + THAI_CARD)
            if sw1 != 0x90 and sw1 != 0x61:
                print(f"💳 [SmartCard] Select applet failed: {sw1:02X} {sw2:02X}")
                return None
                
            # Setup GET RESPONSE prefix depending on ATR
            if atr and len(atr) > 1 and atr[0] == 0x3B and atr[1] == 0x67:
                req = [0x00, 0xc0, 0x00, 0x01]
            else:
                req = [0x00, 0xc0, 0x00, 0x00]

            def get_data(cmd):
                # Transmit APDU CMD, then fetch bytes with dynamic GET RESPONSE prefix
                _, sw1, sw2 = connection.transmit(cmd)
                response, sw1, sw2 = connection.transmit(req + [cmd[-1]])
                return response

            # Read all fields
            cid = self.thai2unicode(get_data(CMD_CID))
            name_th = self.thai2unicode(get_data(CMD_THFULLNAME))
            name_en = self.thai2unicode(get_data(CMD_ENFULLNAME))
            dob = self.thai2unicode(get_data(CMD_BIRTH))
            gender = self.thai2unicode(get_data(CMD_GENDER))
            gender_text = "ชาย" if gender == "1" else "หญิง" if gender == "2" else gender
            card_issuer = self.thai2unicode(get_data(CMD_ISSUER))
            issue_date = self.thai2unicode(get_data(CMD_ISSUE))
            expire_date = self.thai2unicode(get_data(CMD_EXPIRE))
            
            raw_address = self.thai2unicode(get_data(CMD_ADDRESS))
            address_parsed = self.parse_address(raw_address)

            # Read and reconstruct Base64 Photo
            photo = []
            for cmd in PHOTO_CMDS:
                photo += get_data(cmd)
                
            base64_photo = base64.b64encode(bytes(photo)).decode('utf-8')

            return {
                "id": cid,
                "cid": cid,
                "fullname": name_th,
                "name_th": name_th,
                "name_en": name_en,
                "dob": dob,
                "gender": gender_text,
                "card_issuer": card_issuer,
                "issue_date": issue_date,
                "expire_date": expire_date,
                "address": address_parsed,
                "img": base64_photo
            }

        try:
            return await loop.run_in_executor(None, blocking_read)
        except Exception as e:
            print(f"💳 [SmartCard] Error reading card data: {e}")
            return None

    async def run_simulation(self):
        print("💳 [SmartCard] SmartCard Reader Service started (SIMULATED MODE)")
        mock_names_th = ["นาย สมชาย ใจดี", "นางสาว สมหญิง รักเรียน", "นาย กิตติพงษ์ สว่างจิต", "นางสาว พรทิพย์ สวยงาม"]
        mock_names_en = ["Mr. Somchai Jaidee", "Miss Somying Rakrian", "Mr. Kittipong Sawangjit", "Miss Porntip Suayngam"]
        
        while self.is_running:
            # Wait 20 seconds before simulating a card insert (reduced for quicker testing)
            await asyncio.sleep(20)
            if not self.is_running:
                break
                
            print("💳 [SmartCard] Simulation: Citizen ID Card Inserted")
            self.card_present = True
            
            # Send mock data
            idx = random.randint(0, len(mock_names_th) - 1)
            cid = f"1{random.randint(100000000000, 999999999999)}"
            mock_data = {
                "id": cid,
                "cid": cid,
                "fullname": mock_names_th[idx],
                "name_th": mock_names_th[idx],
                "name_en": mock_names_en[idx],
                "dob": "25330101",
                "gender": "ชาย" if "นาย" in mock_names_th[idx] else "หญิง",
                "card_issuer": "ที่ว่าการอำเภอเมืองเชียงใหม่",
                "issue_date": "25650510",
                "expire_date": "25750509",
                "address": {
                    "raw": "123/4 หมู่ที่ 5 ถนนเชียงใหม่-หางดง ตำบลสุเทพ อำเภอเมืองเชียงใหม่ จังหวัดเชียงใหม่",
                    "house_no": "123/4",
                    "moo": "5",
                    "road": "เชียงใหม่-หางดง",
                    "tambon": "สุเทพ",
                    "amphoe": "เมืองเชียงใหม่",
                    "province": "เชียงใหม่"
                },
                "img": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            }
            
            await self.state_manager.handle_card_insert(mock_data)
            
            # Keep card inserted for 12 seconds, then simulate remove
            await asyncio.sleep(12)
            if not self.is_running:
                break
                
            print("💳 [SmartCard] Simulation: Citizen ID Card Removed")
            self.card_present = False
            await self.state_manager.handle_card_remove()

    async def handle_card_added(self, card):
        if self.card_present:
            return
        print("💳 [SmartCard] Citizen Card Inserted (via CardMonitor)")
        self.card_present = True
            
        loop = asyncio.get_running_loop()
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                connection = card.createConnection()
                # Wait for card contacts and voltage to stabilize
                await asyncio.sleep(0.3 if attempt == 1 else 0.5)
                await loop.run_in_executor(None, connection.connect)
                atr = connection.getATR()
                card_data = await self.read_card_data(connection, atr)
                if card_data:
                    await self.state_manager.handle_card_insert(card_data)
                    return
                else:
                    print(f"💳 [SmartCard] Failed to read citizen card data (attempt {attempt}/{max_retries}).")
            except Exception as e:
                print(f"💳 [SmartCard] Error connecting/reading card on insertion (attempt {attempt}/{max_retries}): {e}")
            
            if attempt < max_retries:
                print("💳 [SmartCard] Retrying card connection...")
                
        # If all retries failed, reset card_present so it can be re-triggered
        print("💳 [SmartCard] All insertion read attempts failed. Resetting card state.")
        self.card_present = False

    async def handle_card_removed(self):
        if not self.card_present:
            return
        print("💳 [SmartCard] Citizen Card Removed (via CardMonitor)")
        self.card_present = False
        await self.state_manager.handle_card_remove()

    async def run_hardware(self):
        print("💳 [SmartCard] SmartCard Reader Service started (PC/SC HARDWARE MODE)")
        loop = asyncio.get_running_loop()
        pcsc_fail_count = 0
        
        while self.is_running:
            monitor = None
            observer = None
            try:
                # Setup CardMonitor and Observer
                monitor = CardMonitor()
                observer = KioskCardObserver(self, loop)
                monitor.addObserver(observer)
                pcsc_fail_count = 0
                
                while self.is_running:
                    # Reader check loop to monitor hardware connection state
                    try:
                        reader_list = await loop.run_in_executor(None, readers)
                        if reader_list:
                            name = reader_list[0].name
                            if self.reader_name != name:
                                self.reader_name = name
                                print(f"💳 [SmartCard] Detected SmartCard Reader: {name}")
                        else:
                            if self.reader_name is not None:
                                print("💳 [SmartCard] SmartCard Reader disconnected.")
                                self.reader_name = None
                    except Exception as e:
                        print(f"💳 [SmartCard] Error checking reader status: {e}")
                        raise e
                    
                    await asyncio.sleep(5)
                    
            except Exception as e:
                print(f"💳 [SmartCard] SmartCard monitor loop error: {e}")
                pcsc_fail_count += 1
                
                if monitor and observer:
                    try:
                        monitor.deleteObserver(observer)
                    except Exception:
                        pass
                
                # Self-healing if offline or successive failures
                if "Service not available" in str(e) or "0x8010001D" in str(e) or pcsc_fail_count >= 2:
                    print(f"💳 [SmartCard] Resource Manager offline. Fail counter: {pcsc_fail_count}/2")
                    print("💳 [SmartCard] Attempting auto-recovery (USB reset + pcscd restart)...")
                    try:
                        await loop.run_in_executor(None, reset_usb_reader)
                        proc = await asyncio.create_subprocess_exec(
                            "sudo", "systemctl", "restart", "pcscd",
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL
                        )
                        await proc.wait()
                        print("💳 [SmartCard] pcscd daemon restarted successfully.")
                    except Exception as ex:
                        print(f"💳 [SmartCard] Auto-recovery failed: {ex}")
                    pcsc_fail_count = 0

                try:
                    from smartcard.pcsc.PCSCContext import PCSCContext
                    PCSCContext.instance = None
                    print("💳 [SmartCard] PCSCContext reset completed.")
                except Exception as ex:
                    pass
                await asyncio.sleep(5)
            finally:
                if monitor and observer:
                    try:
                        monitor.deleteObserver(observer)
                    except Exception:
                        pass

    async def start(self):
        self.is_running = True
        # If force mock or pyscard is missing, start simulation
        force_mock = os.getenv("MOCK_SMARTCARD", "0") == "1"
        if force_mock or not PYSCARD_AVAILABLE:
            self.task = asyncio.create_task(self.run_simulation())
        else:
            self.task = asyncio.create_task(self.run_hardware())

    async def stop(self):
        self.is_running = False
        self.reader_name = None
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        print("💳 [SmartCard] SmartCard Reader Service stopped.")
