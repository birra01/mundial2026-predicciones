#!/usr/bin/env python3
"""Sube la captura de apuesta ganada al canal @playerostips (caption + foto).
NO modifica bot.py: usa BOT_TOKEN del .env del bot."""
import sys, asyncio
from pathlib import Path

BOT_ENV = Path.home() / "bot_apuestas" / ".env"
CANAL_CHAT_ID = -1004315028306
IMG = Path.home() / "Imágenes" / "telegramAPUESTAS" / "Captura de pantalla_20260712_000016.png"

token = None
for line in BOT_ENV.read_text().splitlines():
    s = line.strip()
    if s.startswith("BOT_TOKEN="):
        token = s.split("=", 1)[1].strip().strip('"').strip("'"); break
assert token, "sin BOT_TOKEN"
assert IMG.exists(), f"falta imagen {IMG}"

caption = (
"🟢 ¡PRIMERA PARTE Y APUESTA YA GANADA!\n\n"
"⚽ Noruega vs Inglaterra — Cuartos de Final\n\n"
"🔥 La combinamos con remate a puerta de Haaland y Kane para aprovechar "
"el superaumento de Bet365 📈\n\n"
"💎 ¿Quieres más combinadas verdes como esta? Entra en nuestro Telegram Premium 🔒\n\n"
"#Mundial2026 #NoruegaInglaterra #ApuestaGanada #Bet365"
)

sys.path.insert(0, str(Path.home()/"bot_apuestas"/"venv"/"lib"/"python3.14"/"site-packages"))
from telegram import Bot

async def main():
    bot = Bot(token=token)
    msg = await bot.send_photo(chat_id=CANAL_CHAT_ID, photo=IMG.open("rb"), caption=caption, parse_mode=None)
    print("ENVIADO ok, message_id=", msg.message_id)

asyncio.run(main())
