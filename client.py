# client.py
import asyncio
import websockets
import json

async def main():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        while True:
            msg = await ws.recv()
            try:
                data = json.loads(msg)
                print("📨 Received:", json.dumps(data, indent=2))
            except:
                print("📨 Received (raw):", msg)

asyncio.run(main())
