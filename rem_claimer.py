import os
import sys
import asyncio
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord

# ─── Environment Variables ────────────────────────────────────────────
TOKENS = [t.strip() for t in os.getenv("TOKENS", "").split(",") if t.strip()]
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
MUDAE_BOT_ID = 432610292342587392
CLAIM_EMOJIS = ["💖", "💗", "💘", "❤️", "💓", "💕", "♥️"]
TARGET_CHAR = "rem"          # case‑insensitive

# ─── HTTP Server (for Render health checks) ──────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass   # keep logs clean

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("0.0.0.0", port), HealthHandler)
    httpd.serve_forever()

# ─── Discord Client per Account ──────────────────────────────────────
async def run_account(token: str):
    client = discord.Client()
    processed = set()
    attempting = False

    @client.event
    async def on_ready():
        print(f"✅ {client.user.name} is online and watching.")

    @client.event
    async def on_message(message):
        nonlocal attempting

        if message.author.id != MUDAE_BOT_ID or message.channel.id != CHANNEL_ID:
            return
        if not message.embeds:
            return

        embed = message.embeds[0]
        if not embed.author or embed.author.name.lower() != TARGET_CHAR:
            return

        if message.id in processed or attempting:
            return

        claim_button = None
        for component in message.components:
            for btn in component.children:
                if hasattr(btn, "emoji") and btn.emoji and btn.emoji.name in CLAIM_EMOJIS:
                    claim_button = btn
                    break
            if claim_button:
                break

        if not claim_button:
            return

        processed.add(message.id)
        attempting = True
        try:
            await attempt_claim(client, message, claim_button)
        finally:
            attempting = False

    async def attempt_claim(client, msg, btn, used_rt=False):
        # small stagger to avoid all accounts clicking at the exact same time
        await asyncio.sleep(random.uniform(0, 0.5))

        await btn.click()
        print(f"💖 {client.user.name} clicked claim on {TARGET_CHAR} (msg {msg.id})")

        await asyncio.sleep(2)

        failure_phrase = "you can't claim"
        failure_found = False
        async for m in msg.channel.history(limit=5):
            if m.author.id == MUDAE_BOT_ID and failure_phrase in m.content.lower():
                failure_found = True
                break

        if not failure_found:
            print(f"✅ {client.user.name} claimed successfully!")
            return

        if used_rt:
            print(f"❌ {client.user.name} still can't claim even after $rt.")
            return

        print(f"🔄 {client.user.name} got 'you can\'t claim' – sending $rt...")
        await msg.channel.send("$rt")
        await asyncio.sleep(3)

        rt_cooldown_phrase = "$rt cooldown is not over"
        rt_fail = False
        async for m in msg.channel.history(limit=5):
            if m.author.id == MUDAE_BOT_ID and rt_cooldown_phrase in m.content.lower():
                rt_fail = True
                break

        if rt_fail:
            print(f"⏳ {client.user.name} $rt is on cooldown – giving up.")
            return

        try:
            fresh_msg = await msg.channel.fetch_message(msg.id)
            new_btn = None
            for comp in fresh_msg.components:
                for b in comp.children:
                    if hasattr(b, "emoji") and b.emoji and b.emoji.name in CLAIM_EMOJIS:
                        new_btn = b
                        break
                if new_btn:
                    break
            if new_btn:
                print(f"🔁 {client.user.name} retrying claim after $rt...")
                await attempt_claim(client, fresh_msg, new_btn, used_rt=True)
            else:
                print(f"⚠️ {client.user.name} could not find claim button after $rt.")
        except discord.NotFound:
            print(f"⚠️ {client.user.name} original message was deleted.")

    await client.start(token)

# ─── Main entry point ──────────────────────────────────────────────────
async def main():
    if not TOKENS:
        print("❌ No tokens found. Set TOKENS environment variable.")
        return
    if CHANNEL_ID == 0:
        print("❌ No CHANNEL_ID set.")
        return

    print(f"🚀 Starting {len(TOKENS)} accounts on channel {CHANNEL_ID}")
    tasks = [asyncio.create_task(run_account(tok)) for tok in TOKENS]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    # Start web server in a daemon thread
    threading.Thread(target=run_webserver, daemon=True).start()

    # Run the bot with automatic restart on crash
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            print(f"⚠️ Bot crashed: {e}. Restarting in 10s...")
            import time
            time.sleep(10)
