#!/usr/bin/env python3
"""Sube la previa de Argentina-Suiza al canal @playerostips.
NO modifica bot.py: usa BOT_TOKEN del .env del bot."""
import sys, asyncio
from pathlib import Path

BOT_ENV = Path.home() / "bot_apuestas" / ".env"
CANAL_CHAT_ID = -1004315028306
PREVIA = Path.home() / "Documentos" / "herramientas apuestas" / "data" / "previas" / "argentina_suiza_12jul.md"

token = None
for line in BOT_ENV.read_text().splitlines():
    s = line.strip()
    if s.startswith("BOT_TOKEN="):
        token = s.split("=", 1)[1].strip().strip('"').strip("'"); break
assert token, "sin BOT_TOKEN"
assert PREVIA.exists(), f"falta previa {PREVIA}"

texto = PREVIA.read_text(encoding="utf-8")
assert len(texto) <= 4096, f"previa muy larga: {len(texto)}"

sys.path.insert(0, str(Path.home()/"bot_apuestas"/"venv"/"lib"/"python3.14"/"site-packages"))
from telegram import Bot

async def main():
    bot = Bot(token=token)
    msg = await bot.send_message(chat_id=CANAL_CHAT_ID, text=texto, parse_mode=None)
    print("ENVIADO ok, message_id=", msg.message_id)

asyncio.run(main())
