import os
import asyncio
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "").strip()
ADMIN_ID = 1858295769

sdk = mercadopago.SDK(MP_ACCESS_TOKEN) if MP_ACCESS_TOKEN else None
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_FILE = "x360_store.db"

CATEGORIAS = {
    "gratis": "🎁 Desbloqueios Gratis",
    "acao": "💥 Acao",
    "aventura": "🗺️ Aventura",
    "corrida": "🚗 Corrida",
    "luta": "🥊 Luta",
    "fps": "🎯 FPS",
    "tiro": "🔫 Tiro",
    "esportes": "⚽ Esportes",
    "mundo_aberto": "🌆 Mundo Aberto",
    "plataforma": "🧱 Plataforma",
    "terror": "🧟 Terror",
    "rpg": "🧙 RPG",
    "kinect": "🕺 Kinect",
}

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
        await db.execute("DELETE FROM jogos WHERE id = 'vip_total' OR nome LIKE '%VIP%'")
        await db.execute("DELETE FROM jogos WHERE id = 'rockband_pack'")
        await db.execute("""
            INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao)
            VALUES 
            ('badavatar', 'Desbloqueio via BadAvatar', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Guia e ficheiros para desbloqueio via exploit BadAvatar.'),
            ('rockband', 'Desbloqueio via Rock Band', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Ficheiros essenciais para desbloqueio via exploit Rock Band.')
            ON CONFLICT(id) DO UPDATE SET
                nome=excluded.nome,
                descricao=excluded.descricao
        """)
        await db.commit()

def menu_principal():
    kb = [
        [InlineKeyboardButton(text="🎁 Desbloqueios Gratis (Rock Band / BadAvatar)", callback_data="cat_gratis_1")],
        [InlineKeyboardButton(text="📂 Catalogo de Jogos (GOD / XEX)", callback_data="menu_categorias")],
        [InlineKeyboardButton(text="🔍 Como Pesquisar por Nome", callback_data="ajuda_busca")],
        [InlineKeyboardButton(text="📖 Como Instalar (Tutorial Pendrive)", callback_data="tutorial_instalacao")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def menu_categorias_markup():
    kb = [
        [InlineKeyboardButton(text="💥 Acao", callback_data="cat_acao_1"), InlineKeyboardButton(text="🗺️ Aventura", callback_data="cat_aventura_1")],
        [InlineKeyboardButton(text="🚗 Corrida", callback_data="cat_corrida_1"), InlineKeyboardButton(text="🥊 Luta", callback_data="cat_luta_1")],
        [InlineKeyboardButton(text="🎯 FPS", callback_data="cat_fps_1"), InlineKeyboardButton(text="🔫 Tiro", callback_data="cat_tiro_1")],
        [InlineKeyboardButton(text="⚽ Esportes", callback_data="cat_esportes_1"), InlineKeyboardButton(text="🌆 Mundo Aberto", callback_data="cat_mundo_aberto_1")],
        [InlineKeyboardButton(text="🧱 Plataforma", callback_data="cat_plataforma_1"), InlineKeyboardButton(text="🧟 Terror", callback_data="cat_terror_1")],
        [InlineKeyboardButton(text="🧙 RPG", callback_data="cat_rpg_1"), InlineKeyboardButton(text="🕺 Kinect", callback_data="cat_kinect_1")],
        [InlineKeyboardButton(text="🎁 Ver Desbloqueios Gratuitos", callback_data="cat_gratis_1")],
        [InlineKeyboardButton(text="🔙 ❮ VOLTAR AO INICIO ❯", callback_data="voltar_inicio")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def menu_jogos_categoria(cat_key, pagina=1):
    itens_por_pag = 6
    offset = (pagina - 1) * itens_por_pag

    async with aiosqlite.connect(DB_FILE) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM jogos WHERE categoria = ?", (cat_key,))
        total_jogos = (await c1.fetchone())[0]

        c2 = await db.execute(
            "SELECT id, nome, preco FROM jogos WHERE categoria = ? ORDER BY nome ASC LIMIT ? OFFSET ?",
            (cat_key, itens_por_pag, offset)
        )
        jogos = await c2.fetchall()

    kb = []
    for j_id, nome, preco in jogos:
        rotulo = "GRATIS" if preco == 0.0 else f"R$ {preco:.2f}"
        icone = "🎁" if preco == 0.0 else "🎮"
        kb.append([InlineKeyboardButton(text=f"{icone} {nome} | {rotulo}", callback_data=f"info_{j_id}")])

    total_paginas = max(1, (total_jogos + itens_por_pag - 1) // itens_por_pag)
    linha_nav = []
    if pagina > 1:
        linha_nav.append(InlineKeyboardButton(text="⬅️ Anterior", callback_data=f"cat_{cat_key}_{pagina - 1}"))
    if total_paginas > 1:
        linha_nav.append(InlineKeyboardButton(text=f"📄 {pagina}/{total_paginas}", callback_data="noop"))
    if pagina < total_paginas:
        linha_nav.append(InlineKeyboardButton(text="Proxima ➡️", callback_data=f"cat_{cat_key}_{pagina + 1}"))
    if linha_nav:
        kb.append(linha_nav)

    kb.append([InlineKeyboardButton(text="🔙 ❮ VOLTAR AS CATEGORIAS ❯", callback_data="menu_categorias")])
    return InlineKeyboardMarkup(inline_keyboard=kb), total_jogos

@dp.message(Command("novojogo"))
async def cmd_novo_jogo(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    texto = message.text.replace("/novojogo", "").strip()
    partes = [p.strip() for p in texto.split("|")]

    if len(partes) < 6:
        cats = ", ".join([f"`{k}`" for k in CATEGORIAS.keys()])
        await message.answer(f"Formato: `/novojogo id | Nome | cat | preco | link | desc`\nCats: {cats}", parse_mode="Markdown")
        return

    j_id, nome, cat, preco_str, link, desc = partes[0].lower(), partes[1], partes[2].lower(), partes[3], partes[4], partes[5]

    if cat not in CATEGORIAS:
        await message.answer("❌ Categoria invalida.")
        return

    try:
        preco = float(preco_str.replace(",", "."))
    except ValueError:
        await message.answer("❌ Preco invalido.")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nome=excluded.nome,
                categoria=excluded.categoria,
                preco=excluded.preco,
                link_download=excluded.link_download,
                descricao=excluded.descricao
        """, (j_id, nome, cat, preco, link, desc))
        await db.commit()

    rotulo = "GRATIS" if preco == 0.0 else f"R$ {preco:.2f}"
    await message.answer(f"✅ Cadastrado: **{nome}** ({rotulo})", parse_mode="Markdown")

@dp.message(CommandStart())
async def cmd_start(message: Message):
    texto = (
        "🎮 **Bem-vindo a X360 TECH BR!**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ **SEU XBOX 360 AINDA VIVE!** ⚡\n\n"
        "Jogos digitais prontos para pendrive ou HD interno.\n"
        "Baixe em alta velocidade sem encurtadores ou virus!\n\n"
        "🟢 Formato GOD / XEX testado para RGH e JTAG\n"
        "🎁 Desbloqueios e utilitarios gratuitos disponiveis\n"
        "📥 Download direto e seguro via Telegram\n"
        "⚡ Pagamento automatizado via Pix com entrega imediata\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 _Escolha uma categoria ou pesquise o seu jogo favorito:_"
    )
    await message.answer(texto, reply_markup=menu_principal(), parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_buscar(message: Message):
    termo = message.text.replace("/buscar", "").strip()
    if not termo:
        await message.answer("🔍 Envie `/buscar` seguido do nome do jogo.", parse_mode="Markdown")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT id, nome, preco FROM jogos WHERE nome LIKE ?
