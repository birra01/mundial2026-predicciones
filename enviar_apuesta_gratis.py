#!/usr/bin/env python3
"""Sube la apuesta del dia (BTTS Si, España-Francia) + imagen al canal @playerostips.
NO modifica bot.py: usa BOT_TOKEN del .env del bot y envia al canal -1004315028306."""
import sys, asyncio
from pathlib import Path

BOT_ENV = Path.home() / "bot_apuestas" / ".env"
CANAL_CHAT_ID = -1004315028306
IMG = Path.home() / "Imágenes" / "telegramAPUESTAS" / "ChatGPT Image 14 jul 2026, 13_57_46.png"

token = None
for line in BOT_ENV.read_text().splitlines():
    s = line.strip()
    if s.startswith("BOT_TOKEN="):
        token = s.split("=", 1)[1].strip().strip('"').strip("'"); break
assert token, "sin BOT_TOKEN"
assert IMG.exists(), f"falta imagen {IMG}"

caption = (
"🎁 APUESTA DEL DÍA\n"
"⚽ España vs Francia — SEMIFINAL Mundial 2026\n"
"📅 Hoy 14 julio · 21:00 CEST\n\n"
"🔥 MERCADO: Ambos equipos marcarán — SÍ\n"
"💰 Cuota: 1.66 (bet365)\n\n"
"📊 Por qué: a 1.66 cobras mejor que el consenso de las casas (TopMercato 1.85, Eurosport 1.75). "
"Ataques élite — Mbappé (8 goles), Oyarzabal, Yamal, Merino vs Dembélé/Olise — y el H2H reciente "
"fue 5-4 y 2-1. El riesgo: Francia 0 goles encajados en sus 3 eliminatorias y Unai Simón lleva "
"649' imbatido; en semifinales se cierran. Valor real, pero no es segura.\n\n"
"🔞 Juega con responsabilidad. +18\n"
"#Mundial2026 #EspanaFrancia #ApuestaDelDia"
)

sys.path.insert(0, str(Path.home()/"bot_apuestas"/"venv"/"lib"/"python3.14"/"site-packages"))
from telegram import Bot

async def main():
    bot = Bot(token=token)
    msg = await bot.send_photo(chat_id=CANAL_CHAT_ID, photo=IMG.open("rb"), caption=caption, parse_mode=None)
    print("ENVIADO ok, message_id=", msg.message_id)

asyncio.run(main())
