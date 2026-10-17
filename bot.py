import os, asyncio, urllib.parse, aiosqlite, mercadopago
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, InlineKeyboardButton as IKB, InlineKeyboardMarkup as IKM, Message

TOKEN = os.getenv("BOT_TOKEN", "").strip()
MP_KEY = os.getenv("MP_ACCESS_TOKEN", "").strip()
ADMIN_ID = 1858295769

sdk = mercadopago.SDK(MP_KEY) if MP_KEY else None
bot, dp, DB = Bot(token=TOKEN), Dispatcher(), "x360_store.db"

TXT_INI = (
    "🎮 **X360 TECH BR | Loja Oficial**\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚡ O seu Xbox 360 no nivel maximo!\n\n"
    "🟢 **Entrega Automatica via Pix** (24/7)\n"
    "📦 **Formatos:** GOD e XEX p/ Pendrive/HD\n"
    "🎁 **Desbloqueios e Dashboards Gratuitos**\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "👇 _Toque numa opcao abaixo:_"
)

CATS = {
    "gratis": "🎁 Desbloqueios", "acao": "💥 Acao", "aventura": "🗺️ Aventura",
    "corrida": "🚗 Corrida", "luta": "🥊 Luta", "
