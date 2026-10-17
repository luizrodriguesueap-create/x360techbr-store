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

ADMIN_ID = 1858295769  # Seu ID de administrador

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_FILE = "x360_store.db"

# 12 Categorias Oficiais
CATEGORIAS = {
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
        await db.commit()

# ================= MENUS =================
async def menu_principal():
    botoes = [
        [InlineKeyboardButton(text="📂 Ver Categorias de Jogos", callback_data="menu_categorias")],
        [InlineKeyboardButton(text="🔍 Como Pesquisar por Nome", callback_data="ajuda_busca")],
        [InlineKeyboardButton(text="📖 Como Instalar (Tutorial Pendrive)", callback_data="tutorial_instalacao")]
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
        [InlineKeyboardButton(text="◀️ Voltar ao Início", callback_data="voltar_inicio")]
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
        botoes.append([InlineKeyboardButton(text=f"🎮 {nome} | R$ {preco:.2f}", callback_data=f"info_{jogo_id}")])

    total_paginas = max(1, (total_jogos + itens_por_pag - 1) // itens_por_pag)
    
    linha_nav = []
    if pagina > 1:
        linha_nav.append(InlineKeyboardButton(text="⬅️ Anterior", callback_data=f"cat_{cat_key}_{pagina - 1}"))
    if total_paginas > 1:
        linha_nav.append(InlineKeyboardButton(text=f"📄 {pagina}/{total_paginas}", callback_data="noop"))
    if pagina < total_paginas:
        linha_nav.append(InlineKeyboardButton(text="Próxima ➡️", callback_data=f"cat_{cat_key}_{pagina + 1}"))
    
    if linha_nav:
        botoes.append(linha_nav)

    botoes.append([InlineKeyboardButton(text="📂 Voltar às Categorias", callback_data="menu_categorias")])
    return InlineKeyboardMarkup(inline_keyboard=botoes), total_jogos

# ================= COMANDOS ADMIN =================
@dp.message(Command("novojogo"))
async def cmd_novo_jogo(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    texto = message.text.replace("/novojogo", "").strip()
    partes = [p.strip() for p in texto.split("|")]

    if len(partes) < 6:
        cats_disponiveis = ", ".join([f"`{k}`" for k in CATEGORIAS.keys()])
        exemplo = "`/novojogo gta5 | GTA V Completo | mundo_aberto | 9.90 | https://t.me/+linkDoJogo | 🎙️ Legendas PT-BR. Formato GOD pronto para pendrive.`"
        await message.answer(
            f"⚠️ **Formato incorreto!** Use os 6 campos separados por barras `|`:\n\n{exemplo}\n\n**Categorias aceites:**\n{cats_disponiveis}",
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
        cats_disponiveis = ", ".join([f"`{k}`" for k in CATEGORIAS.keys()])
        await message.answer(f"❌ Categoria inválida! Escolha uma destas:\n{cats_disponiveis}", parse_mode="Markdown")
        return

    try:
        preco = float(preco_str.replace(",", "."))
    except ValueError:
        await message.answer("❌ O preço deve ser um número (ex: 9.90).")
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

    nome_cat = CATEGORIAS[categoria][0]
    await message.answer(
        f"✅ **Jogo adicionado à loja!**\n\n"
        f"🎮 **Nome:** {nome}\n"
        f"📂 **Categoria:** {nome_cat}\n"
        f"💰 **Preço:** R$ {preco:.2f}\n"
        f"🔗 **Link:** `{link_download}`\n"
        f"📝 **Detalhes:** {descricao}",
        parse_mode="Markdown"
    )

# ================= FLUXO DO CLIENTE =================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    markup = await menu_principal()
    texto = (
        "🎮 **Bem-vindo à X360 TECH BR!**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ **SEU XBOX 360 AINDA VIVE!** ⚡\n\n"
        "Jogos digitais prontos para pendrive ou HD interno.\n"
        "Baixe em alta velocidade sem encurtadores, vírus ou espera!\n\n"
        "🟢 Formato GOD / RGH 100% testado\n"
        "📥 Download direto e seguro via Telegram\n"
        "⚡ Pagamento automatizado via Pix com entrega imediata\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 _Escolha uma categoria ou pesquise o seu jogo favorito:_"
    )
    await message.answer(texto, reply_markup=markup, parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_buscar(message: Message):
    termo = message.text.replace("/buscar", "").strip()
    if not termo:
        await message.answer("🔍 Digite o nome do jogo que deseja buscar. Exemplo:\n`/buscar gta` ou `/buscar resident`", parse_mode="Markdown")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT id, nome, preco FROM jogos WHERE nome LIKE ? LIMIT 8",
            (f"%{termo}%",)
        )
        jogos = await cursor.fetchall()

    if not jogos:
        await message.answer(f"❌ Nenhum jogo encontrado com o termo **'{termo}'**. Tente uma busca mais simples ou navegue pelas categorias com /start.")
        return

    botoes = []
    for jogo_id, nome, preco in jogos:
        botoes.append([InlineKeyboardButton(text=f"🎮 {nome} | R$ {preco:.2f}", callback_data=f"info_{jogo_id}")])
    botoes.append([InlineKeyboardButton(text="◀️ Voltar ao Início", callback_data="voltar_inicio")])

    await message.answer(f"🔍 **Resultados para '{termo}':**", reply_markup=InlineKeyboardMarkup(inline_keyboard=botoes), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_categorias")
async def cb_menu_categorias(callback: CallbackQuery):
    markup = menu_categorias_markup()
    texto = "📂 **Escolha o género do jogo que procura:**"
    try:
        await callback.message.edit_text(texto, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(texto, reply_markup=markup, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("cat_"))
async def cb_jogos_da_categoria(callback: CallbackQuery):
    partes = callback.data.split("_")
    cat_key = partes[1]
    pagina = int(partes[2])

    markup, total_jogos = await menu_jogos_categoria(cat_key, pagina)
    nome_cat = CATEGORIAS.get(cat_key, ("Categoria", ""))[0]

    if total_jogos == 0:
        texto = (
            f"{nome_cat}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _Ainda não há jogos nesta categoria._\n\n"
            f"Estamos a adicionar novos jogos diariamente! Use `/buscar` para procurar outros títulos ou volte ao início."
        )
    else:
        texto = f"{nome_cat}\n━━━━━━━━━━━━━━━━━━━\nSelecione um jogo para ver os detalhes e fazer o download:"

    try:
        await callback.message.edit_text(texto, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(texto, reply_markup=markup, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("info_"))
async def callback_info(callback: CallbackQuery):
    jogo_id = callback.data.replace("info_", "")

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT nome, preco, descricao, categoria FROM jogos WHERE id = ?", (jogo_id,))
        jogo = await cursor.fetchone()

    if not jogo:
        await callback.answer("Jogo não encontrado.", show_alert=True)
        return

    nome, preco, desc, cat_key = jogo
    texto = (
        f"🎮 **{nome}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📝 **Detalhes:** {desc}\n"
        f"💰 **Valor:** R$ {preco:.2f}\n"
        f"📦 **Formato:** GOD / Pronto para Pendrive ou HD\n"
        f"⚡ **Entrega:** Link de download imediato via Telegram\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Clique abaixo para gerar o Pix e receber na hora:"
    )

    voltar_cb = f"cat_{cat_key}_1" if cat_key in CATEGORIAS else "menu_categorias"
    botoes = [
        [InlineKeyboardButton(text=f"⚡ Pagar R$ {preco:.2f} via Pix", callback_data=f"gerarpix_{jogo_id}")],
        [InlineKeyboardButton(text="⬅️ Voltar", callback_data=voltar_cb)]
    ]
    await callback.message.edit_text(texto, reply_markup=InlineKeyboardMarkup(inline_keyboard=botoes), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("gerarpix_"))
async def process_pix(callback: CallbackQuery):
    jogo_id = callback.data.replace("gerarpix_", "")

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT nome, preco FROM jogos WHERE id = ?", (jogo_id,))
        jogo = await cursor.fetchone()

    if not jogo:
        await callback.answer("Jogo inválido.", show_alert=True)
        return

    nome, preco = jogo
    await callback.message.edit_text("⏳ A gerar o seu Pix com entrega imediata...")

    payment_data = {
        "transaction_amount": float(preco),
        "description": f"X360 Tech - {nome}",
        "payment_method_id": "pix",
        "payer": {
            "email": f"cliente{callback.from_user.id}@gmail.com",
            "first_name": callback.from_user.first_name or "Gamer",
            "last_name": "X360",
        },
    }

    try:
        result = sdk.payment().create(payment_data)
        payment = result.get("response", {})
    except Exception as e:
        await callback.message.edit_text(f"❌ Erro ao comunicar com o Mercado Pago: {e}")
        return

    if "id" not in payment:
        msg = payment.get("message", "Falha na criação do Pix")
        await callback.message.edit_text(f"❌ Erro: `{msg}`", parse_mode="Markdown")
        return

    payment_id = payment["id"]
