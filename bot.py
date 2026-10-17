import asyncio
import os
import urllib.parse
import aiosqlite
import mercadopago
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ================= CONFIGURAÇÕES =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "").strip()
ADMIN_ID = 1858295769

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_FILE = "x360_store.db"

CATEGORIAS = {
    "gratis": ("🎁 Desbloqueios & Utilitários (Grátis)", "Utilitários Grátis"),
    "acao": ("💥 Ação", "Ação"),
    "aventura": ("🗺️ Aventura", "Aventura"),
    "corrida": ("🚗 Corrida", "Corrida"),
    "luta": ("🥊 Luta", "Luta"),
    "fps": ("🎯 FPS", "FPS"),
    "tiro": ("🔫 Tiro", "Tiro"),
    "esportes": ("⚽ Esportes", "Esportes"),
    "mundo_aberto": ("🌆 Mundo Aberto", "Mundo Aberto"),
    "plataforma": ("🧱 Plataforma", "Plataforma"),
    "terror": ("🧟 Terror", "Terror"),
    "rpg": ("🧙 RPG", "RPG"),
    "kinect": ("🕺 Kinect", "Kinect"),
}

# ================= BASE DE DADOS =================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jogos (
                id TEXT PRIMARY KEY,
                nome TEXT,
                categoria TEXT,
                preco REAL,
                link_download TEXT,
                descricao TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                payment_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                jogo_id TEXT,
                status TEXT
            )
        """)
        # Elimina registos residuais antigos
        await db.execute("DELETE FROM jogos WHERE id = 'vip_total' OR nome LIKE '%VIP%'")
        await db.execute("DELETE FROM jogos WHERE id = 'rockband_pack'")

        # Insere com a nomenclatura técnica correta
        await db.execute(
            """
            INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao)
            VALUES 
            ('badavatar', 'Desbloqueio via BadAvatar', 'gratis', 0.0, 'https://t.me/+SEU_LINK_AQUI', 'Ficheiros completos e guia para executar o desbloqueio via exploit BadAvatar no Xbox 360.'),
            ('rockband', 'Desbloqueio via Rock Band', 'gratis', 0.0, 'https://t.me/+SEU_LINK_AQUI', 'Ficheiros essenciais para ativação e carregamento do desbloqueio via exploit Rock Band.')
            ON CONFLICT(id) DO UPDATE SET
                nome=excluded.nome,
                descricao=excluded.descricao
            """
        )
        await db.commit()

# ================= MENUS =================
async def menu_principal():
    botoes =
