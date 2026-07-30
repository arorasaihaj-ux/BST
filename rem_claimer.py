import os
import sys
import asyncio
import random
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord

# ─── Environment ──────────────────────────────────────────────────────
TOKENS = [t.strip() for t in os.getenv("TOKENS", "").split(",") if t.strip()]
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
MUDAE_BOT_ID = 432610292342587392
CLAIM_EMOJIS = ["💖", "💗", "💘", "❤️", "💓", "💕", "♥️"]
TARGET_CHAR = "rem"

# ─── HTTP Server (Render health) ─────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("0.0.0.0", port), HealthHandler)
    httpd.serve_forever()

# ─── Per‑account client ──────────────────────────────────────────────
class ClaimClient(discord.Client):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.processed = set()
        self.max_processed = 1000          # memory cap
        self.attempting = False
        self.rate_limited_until = 0

    async def on_ready(self):
        print(f"✅ {self.user.name} online – watching channel {CHANNEL_ID} only")

    async def on_message(self, msg):
        # Ignore everything outside our single channel
        if msg.channel.id != CHANNEL_ID:
            return
        if msg.author.id != MUDAE_BOT_ID:
            return
        if not msg.embeds:
            return

        embed = msg.embeds[0]
        if not embed.author or embed.author.name.lower() != TARGET_CHAR:
            return

        # Prevent re‑processing same message
        if msg.id in self.processed:
            return
        if self.attempting:
            return

        # Find claim button
        claim_btn = None
        for comp in msg.components:
            for btn in comp.children:
                if hasattr(btn, "emoji") and btn.emoji and btn.emoji.name in CLAIM_EMOJIS:
                    claim_btn = btn
                    break
            if claim_btn:
                break
        if not claim_btn:
            return

        # Mark as processed (memory cap)
        self.processed.add(msg.id)
        if len(self.processed) > self.max_processed:
            # Remove oldest (roughly)
            to_remove = len(self.processed) - self.max_processed
            for _ in range(to_remove):
                self.processed.pop()

        self.attempting = True
        try:
            await self._claim_sequence(msg, claim_btn)
        finally:
            self.attempting = False

    async def _claim_sequence(self, msg, btn, used_rt=False):
        # Random stagger 0–0.5s to reduce race
        await asyncio.sleep(random.uniform(0, 0.5))

        # Click with rate‑limit backoff
        await self._click_with_retry(btn)
        print(f"💖 {self.user.name} clicked claim on {TARGET_CHAR} (msg {msg.id})")

        await asyncio.sleep(2)  # let Mudae reply

        # Check for "you can't claim"
        fail_phrase = "you can't claim"
        failure = False
        async for m in msg.channel.history(limit=5):
            if m.author.id == MUDAE_BOT_ID and fail_phrase in m.content.lower():
                failure = True
                break

        if not failure:
            print(f"✅ {self.user.name} claimed successfully!")
            return

        if used_rt:
            print(f"❌ {self.user.name} still can't claim after $rt")
            return

        # Try $rt
        print(f"🔄 {self.user.name} sending $rt...")
        await self._send_with_retry(msg.channel, "$rt")
        await asyncio.sleep(3)

        # Check if $rt is on cooldown
        rt_cooldown = "$rt cooldown is not over"
        rt_fail = False
        async for m in msg.channel.history(limit=5):
            if m.author.id == MUDAE_BOT_ID and rt_cooldown in m.content.lower():
                rt_fail = True
                break

        if rt_fail:
            print(f"⏳ {self.user.name} $rt cooldown – giving up")
            return

        # Retry with fresh message
        try:
            fresh = await msg.channel.fetch_message(msg.id)
            new_btn = None
            for comp in fresh.components:
                for b in comp.children:
                    if hasattr(b, "emoji") and b.emoji and b.emoji.name in CLAIM_EMOJIS:
                        new_btn = b
                        break
                if new_btn:
                    break
            if new_btn:
                print(f"🔁 {self.user.name} retrying after $rt")
                await self._claim_sequence(fresh, new_btn, used_rt=True)
        except discord.NotFound:
            print(f"⚠️ {self.user.name} message disappeared")

    async def _click_with_retry(self, btn, retries=3):
        for attempt in range(retries):
            now = time.time()
            if now < self.rate_limited_until:
                await asyncio.sleep(self.rate_limited_until - now + 0.5)
            try:
                await btn.click()
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = float(e.retry_after or 5)
                    self.rate_limited_until = time.time() + retry_after
                    print(f"⏳ {self.user.name} rate‑limited, waiting {retry_after:.1f}s")
                    await asyncio.sleep(retry_after + 0.5)
                else:
                    raise

    async def _send_with_retry(self, channel, content, retries=3):
        for attempt in range(retries):
            now = time.time()
            if now < self.rate_limited_until:
                await asyncio.sleep(self.rate_limited_until - now + 0.5)
            try:
                await channel.send(content)
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = float(e.retry_after or 5)
                    self.rate_limited_until = time.time() + retry_after
                    await asyncio.sleep(retry_after + 0.5)
                else:
                    raise

    async def start(self):
        await super().start(self.token, reconnect=True)

# ─── Main ─────────────────────────────────────────────────────────────
async def main():
    if not TOKENS:
        print("❌ No TOKENS set")
        return
    if CHANNEL_ID == 0:
        print("❌ No CHANNEL_ID set")
        return

    print(f"🚀 Starting {len(TOKENS)} accounts on channel {CHANNEL_ID}")
    clients = [ClaimClient(tok) for tok in TOKENS]
    tasks = [client.start() for client in clients]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    threading.Thread(target=run_webserver, daemon=True).start()
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            print(f"⚠️ Crash: {e}. Restarting in 10s...")
            time.sleep(10)
