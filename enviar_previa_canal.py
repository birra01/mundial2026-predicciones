#!/usr/bin/env python3
"""Envía la previa de Noruega-Inglaterra al canal @playerostips.
NO modifica bot.py: usa el BOT_TOKEN del .env del bot y envia al canal.
Uso: python3 enviar_previa_canal.py
"""
import os, sys, asyncio, re
from pathlib import Path

BOT_ENV = Path.home() / "bot_apuestas" / ".env"
CANAL_CHAT_ID = -1004315028306  # @playerostips (de memoria)

# cargar BOT_TOKEN del .env del bot
token = None
if BOT_ENV.exists():
    for line in BOT_ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("BOT_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

if not token:
    print("ERROR: no encontre BOT_TOKEN en", BOT_ENV)
    sys.exit(1)

# importar python-telegram-bot del venv del bot
sys.path.insert(0, str(Path.home() / "bot_apuestas" / "venv" / "lib" / "python3.14" / "site-packages"))

from telegram import Bot

previa = Path(__file__).parent / "data" / "previas" / "noruega_inglaterra_11jul.md"
texto = previa.read_text(encoding="utf-8")

# Telegram limita a 4096 chars por mensaje; la previa cabe de sobra
assert len(texto) <= 4096, f"previa demasiado larga: {len(texto)}"

async def main():
    bot = Bot(token=token)
    # verificar que el bot es admin del canal antes de enviar
    try:
        chat = await bot.get_chat(CANAL_CHAT_ID)
        me = await bot.get_me()
        member = await bot.get_chat_member(CANAL_CHAT_ID, me.id)
        print("Canal:", chat.title, "| bot en canal:", member.status)
        if member.status not in ("administrator", "creator"):
            print("AVISO: el bot no es admin del canal, el envio puede fallar")
    except Exception as e:
        print("No pude verificar membresia:", e)

    msg = await bot.send_message(chat_id=CANAL_CHAT_ID, text=texto, parse_mode=None)
    print("ENVIADO ok, message_id=", msg.message_id)

asyncio.run(main())
