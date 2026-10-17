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

# ================= CONFIGURACOES =================
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
        await db.execute("DELETE FROM jogos WHERE id = 'vip_total' OR nome LIKE '%VIP%'")
        await db.execute("DELETE FROM jogos WHERE id = 'rockband_pack'")

        await db.execute(
            """
            INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao)
            VALUES 
            ('badavatar', 'Desbloqueio via BadAvatar', 'gratis', 0.0, 'https://t.me/+SEU_CANAL_AQUI', 'Arquivos completos e guia para desbloqueio via exploit BadAvatar no Xbox 360.'),
            ('rockband', 'Desbloqueio via Rock Band', 'gratis', 0.0, 'https://t.me/+SEU_CANAL_AQUI', 'Arquivos necessarios para carregamento do desbloqueio via exploit Rock Band.')
            ON CONFLICT(id) DO UPDATE SET
                nome=excluded.nome,
                descricao=excluded.descricao
            """
        )
        await db.commit()

# ================= MENUS MODERNOS =================
async def menu_principal():
    botoes = [
        [InlineKeyboardButton(text="🎁 DESBLOQUEIOS & ARQUIVOS GRÁTIS", callback_data="cat_gratis_1")],
        [InlineKeyboardButton(text="🕹️ CATÁLOGO DE JOGOS (GOD / XEX)", callback_data="menu_categorias")],
        [
            InlineKeyboardButton(text="🔍 Pesquisar Jogo", callback_data="ajuda_busca"),
            InlineKeyboardButton(text="📖 Guia Pendrive/HD", callback_data="tutorial_instalacao")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=botoes)

def menu_categorias_markup():
    botoes = [
        [
            InlineKeyboardButton(text="💥 Ação", callback_data="cat_acao_1"),
            InlineKeyboardButton(text="🗺️ Aventura", callback_data="cat_aventura_1")
        ],
        [
            InlineKeyboardButton(text="🚗 Corrida", callback_data="cat_corrida_1"),
            InlineKeyboardButton(text="🥊 Luta", callback_data="cat_luta_1")
        ],
        [
            InlineKeyboardButton(text="🎯 FPS", callback_data="cat_fps_1"),
            InlineKeyboardButton(text="🔫 Tiro", callback_data="cat_tiro_1")
        ],
        [
            InlineKeyboardButton(text="⚽ Esportes", callback_data="cat_esportes_1"),
            InlineKeyboardButton(text="🌆 Mundo Aberto", callback_data="cat_mundo_aberto_1")
        ],
        [
            InlineKeyboardButton(text="🧱 Plataforma", callback_data="cat_plataforma_1"),
            InlineKeyboardButton(text="🧟 Terror", callback_data="cat_terror_1")
        ],
        [
            InlineKeyboardButton(text="🧙 RPG", callback_data="cat_rpg_1"),
            InlineKeyboardButton(text="🕺 Kinect", callback_data="cat_kinect_1")
        ],
        [InlineKeyboardButton(text="🎁 Ver Desbloqueios Gratuitos", callback_data="cat_gratis_1")],
        [InlineKeyboardButton(text="🔙 ❮ VOLTAR AO MENU PRINCIPAL ❯", callback_data="voltar_inicio")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=botoes)

async def menu_jogos_categoria(cat_key: str, pagina: int = 1):
    itens_por_pag = 6
    offset = (pagina - 1) * itens_por_pag

    async with aiosqlite.connect(DB_FILE) as db:
        cursor_total = await db.execute("SELECT COUNT(*) FROM jogos WHERE categoria = ?", (cat_key,))
        total_jogos = (await cursor_total.fetchone())[0]

        cursor = await db.execute(
            "SELECT id, nome, preco FROM jogos WHERE categoria = ? ORDER BY nome ASC LIMIT ? OFFSET ?",
            (cat_key, itens_por_pag, offset)
        )
        jogos = await cursor.fetchall()

    botoes = []
    for jogo_id, nome, preco in jogos:
        rotulo_preco = "GRÁTIS" if preco == 0.0 else f"R$ {preco:.2f}"
        icone = "🎁" if preco == 0.0 else "💿"
        botoes.append([InlineKeyboardButton(text=f"{icone} {nome}  •  {rotulo_preco}", callback_data=f"info_{jogo_id}")])

    total_paginas = max(1, (total_jogos + itens_por_pag - 1) // itens_por_pag)
    
    linha_nav = []
    if pagina > 1:
        linha_nav.append(InlineKeyboardButton(text="◀️ Anterior", callback_data=f"cat_{cat_key}_{pagina - 1}"))
    if total_paginas > 1:
        linha_nav.append(InlineKeyboardButton(text=f"▫️ {pagina}/{total_paginas} ▫️", callback_data="noop"))
    if pagina < total_paginas:
        linha_nav.append(InlineKeyboardButton(text="Próxima ▶️", callback_data=f"cat_{cat_key}_{pagina + 1}"))
    
    if linha_nav:
        botoes.append(linha_nav)

    botoes.append([InlineKeyboardButton(text="🔙 ❮ VOLTAR ÀS CATEGORIAS ❯", callback_data="menu_categorias")])
    return InlineKeyboardMarkup(inline_keyboard=botoes), total_jogos

# ================= COMANDOS ADMIN =================
@dp.message(Command("novojogo"))
async def cmd_novo_jogo(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    texto = message.text.replace("/novojogo", "").strip()
    partes = [p.strip() for p in texto.split("|")]

    if len(partes) < 6:
        cats = ", ".join([f"`{k}`" for k in CATEGORIAS.keys()])
        await message.answer(
            f"⚠️ **Formato Admin:**\n`/novojogo id | Nome | categoria | preco | link | descricao`\n\n**Categorias:**\n{cats}",
            parse_mode="Markdown"
        )
        return

    jogo_id = partes[0].lower()
    nome = partes[1]
    categoria = partes[2].lower()
    preco_str = partes[3]
    link_download = partes[4]
    descricao = partes[5]

    if categoria not in CATEGORIAS:
        await message.answer("❌ Categoria inválida.")
        return

    try:
        preco = float(preco_str.replace(",", "."))
    except ValueError:
        await message.answer("❌ Preço inválido.")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nome=excluded.nome,
                categoria=excluded.categoria,
                preco=excluded.preco,
                link_download=excluded.link_download,
                descricao=excluded.descricao
            """,
            (jogo_id, nome, categoria, preco, link_download, descricao)
        )
        await db.commit()

    rotulo = "GRÁTIS" if preco == 0.0 else f"R$ {preco:.2f}"
    await message.answer(f"✅ **Cadastrado com Sucesso:**\n🎮 **{nome}** ({rotulo})", parse_mode="Markdown")

# ================= FLUXO PRINCIPAL DO CLIENTE =================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    markup = await menu_principal()
    texto = (
        "🟢 **CENTRAL X360 TECH BR** 🟢\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ *O maior acervo digital para Xbox 360 RGH & JTAG*\n\n"
        "╭─ 📦 **Formatos:** GOD e XEX descompactados\n"
        "├─ 🚀 **Servidores:** Telegram CDN (Sem encurtadores)\n"
        "├─ ⚡ **Pix Automático:** Download liberado na hora\n"
        "╰─ 🎁 **Área Free:** Desbloqueios e ferramentas grátis\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 _Selecione uma opção no menu abaixo para começar:_"
    )
    await message.answer(texto, reply_markup=markup, parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_buscar(message: Message):
    termo = message.text.replace("/buscar", "").strip()
    if not termo:
        await message.answer("🔍 **Como buscar:**\nEnvie `/buscar` e o nome do jogo.\n_Exemplo:_ `/buscar halo`",
