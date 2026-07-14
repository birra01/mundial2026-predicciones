#!/usr/bin/env python3
"""Sube la apuesta gratis del dia (BTTS Si, Noruega-Inglaterra) + imagen al canal.
NO modifica bot.py: usa BOT_TOKEN del .env del bot y envia al canal @playerostips."""
import sys, asyncio
from pathlib import Path

BOT_ENV = Path.home() / "bot_apuestas" / ".env"
CANAL_CHAT_ID = -1004315028306
IMG = Path.home() / "Imágenes" / "telegramAPUESTAS" / "ChatGPT Image 11 jul 2026, 21_15_15.png"

token = None
for line in BOT_ENV.read_text().splitlines():
    s = line.strip()
    if s.startswith("BOT_TOKEN="):
        token = s.split("=", 1)[1].strip().strip('"').strip("'"); break
assert token, "sin BOT_TOKEN"
assert IMG.exists(), f"falta imagen {IMG}"

caption = (
"🎁 APUESTA GRATIS DEL DÍA\n"
"⚽ Noruega vs Inglaterra — Cuartos de Final\n"
"📅 11 julio · 21:00\n\n"
"🔥 MERCADO: Ambos equipos marcarán — SÍ\n"
"💰 Cuota: 1.61 (bet365)\n\n"
"📊 Por qué: xG total 4.28. Noruega mete 2.67 goles/partido y encaja 2.33; "
"Inglaterra 2.0 / 0.67 pero con Kane + Bellingham arriba. El modelo da 66.2% al BTTS Sí.\n\n"
"#Mundial2026 #NoruegaInglaterra #ApuestaGratis"
)

sys.path.insert(0, str(Path.home()/"bot_apuestas"/"venv"/"lib"/"python3.14"/"site-packages"))
from telegram import Bot

async def main():
    bot = Bot(token=token)
    msg = await bot.send_photo(chat_id=CANAL_CHAT_ID, photo=IMG.open("rb"), caption=caption, parse_mode=None)
    print("ENVIADO ok, message_id=", msg.message_id)

asyncio.run(main())
