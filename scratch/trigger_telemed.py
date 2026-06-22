import asyncio
import websockets
import json
import sys

async def main():
    host = "192.168.1.57"
    port = 8765
    print(f"Connecting to ws://{host}:{port}...")
    try:
        async with websockets.connect(f"ws://{host}:{port}") as ws:
            print("Sending trigger_telemedicine_manual...")
            await ws.send(json.dumps({'type': 'trigger_telemedicine_manual'}))
            print("Sent successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
