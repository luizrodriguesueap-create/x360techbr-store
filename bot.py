import os, asyncio, urllib.parse, aiosqlite, mercadopago
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "").strip()
ADMIN_ID = 1858295769

sdk = mercadopago.SDK(MP_ACCESS_TOKEN) if MP_ACCESS_TOKEN else None
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_FILE = "x360_store.db"

TEXTO_BOAS_VINDAS = (
    "🎮 **X360 TECH BR | Loja Oficial**\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚡ O seu Xbox 360 no nível máximo!\n\n"
    "🟢 **Entrega Automática via Pix** (24/7)\n"
    "📦 **Formatos:** GOD e XEX prontos p/ Pendrive/HD\n"
    "🎁 **Desbloqueios e Dashboards Gratuitos**\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "👇 _Toque numa opção abaixo para começar:_"
)

CATEGORIAS = {
    "gratis": "🎁 Desbloqueios",
    "acao": "💥 Ação",
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
    "kinect": "🕺 Kinect"
}

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS jogos (id TEXT PRIMARY KEY, nome TEXT, categoria TEXT, preco REAL, link_download TEXT, descricao TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS pedidos (payment_id INTEGER PRIMARY KEY, user_id INTEGER, jogo_id TEXT, status TEXT)")
        await db.execute("DELETE FROM jogos WHERE categoria IN ('gratis', 'dashboards') OR id IN ('abadavatar', 'badavatar', 'rockband', 'dash_aurora', 'dash_nexus', 'vip_total')")
        
        await db.execute("""
            INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao)
            VALUES 
            ('abadavatar', 'Desbloqueio AbadAvatar', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Guia e ficheiros para o desbloqueio AbadAvatar no Xbox 360.'),
            ('rockband', 'Desbloqueio Rock Band', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Ficheiros essenciais para o desbloqueio Rock Band no Xbox 360.'),
            ('dash_aurora', 'Dashboard Aurora', 'dashboards', 0.0, 'https://t.me/+SEU_CANAL', 'Interface moderna com suporte a capas automáticas, title updates e trainers.'),
            ('dash_nexus', 'Dashboard Nexus', 'dashboards', 0.0, 'https://t.me/+SEU_CANAL', 'Dashboard customizada com menus rápidos, monitor de temperatura e plugins.')
            ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, descricao=excluded.descricao
        """)
        await db.commit()

# ================= DESIGN DOS BOTÕES =================
def btn(texto, cb_data=None, url=None, estilo="primary"):
    kw = {"text": texto}
    if cb_data: kw["callback_data"] = cb_data
    if url: kw["url"] = url
    try:
        return InlineKeyboardButton(**kw, style=estilo)
    except TypeError:
        return InlineKeyboardButton(**kw)

def kb_inicio():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("🟢 Desbloqueios (Grátis)", cb_data="menu_desbloqueios", estilo="success")],
        [btn("🟢 Dashboards (Aurora & Nexus)", cb_data="menu_dashboards", estilo="success")],
        [btn("🔵 Catálogo de Jogos (GOD / XEX)", cb_data="menu_cat", estilo="primary")],
        [
            btn("🔍 Pesquisar Jogo", cb_data="ajuda_busca", estilo="primary"),
            btn("📖 Como Instalar", cb_data="tutorial_inst", estilo="primary")
        ]
    ])

def kb_desbloqueios():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("🟢 Desbloqueio AbadAvatar", cb_data="info_abadavatar", estilo="success")],
        [btn("🟢 Desbloqueio Rock Band", cb_data="info_rockband", estilo="success")],
        [btn("◀️ Voltar ao Início", cb_data="voltar_inicio", estilo="primary")]
    ])

def kb_dashboards():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("🟢 Dashboard Aurora", cb_data="info_dash_aurora", estilo="success")],
        [btn("🟢 Dashboard Nexus", cb_data="info_dash_nexus", estilo="success")],
        [btn("◀️ Voltar ao Início", cb_data="voltar_inicio", estilo="primary")]
    ])

def kb_categorias():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("💥 Ação", cb_data="cat_acao_1"), btn("🗺️ Aventura", cb_data="cat_aventura_1")],
        [btn("🚗 Corrida", cb_data="cat_corrida_1"), btn("🥊 Luta", cb_data="cat_luta_1")],
        [btn("🎯 FPS", cb_data="cat_fps_1"), btn("🔫 Tiro", cb_data="cat_tiro_1")],
        [btn("⚽ Esportes", cb_data="cat_esportes_1"), btn("🌆 Mundo Aberto", cb_data="cat_mundo_aberto_1")],
        [btn("🧱 Plataforma", cb_data="cat_plataforma_1"), btn("🧟 Terror", cb_data="cat_terror_1")],
        [btn("🧙 RPG", cb_data="cat_rpg_1"), btn("🕺 Kinect", cb_data="cat_kinect_1")],
        [btn("🟢 Ver Desbloqueios", cb_data="menu_desbloqueios", estilo="success")],
        [btn("◀️ Voltar ao Início", cb_data="voltar_inicio", estilo="primary")]
    ])

async def kb_jogos(cat_key, pagina=1):
    itens = 6
    offset = (pagina - 1) * itens
    async with aiosqlite.connect(DB_FILE) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM jogos WHERE categoria = ?", (cat_key,))
        total = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT id, nome, preco FROM jogos WHERE categoria = ? ORDER BY nome ASC LIMIT ? OFFSET ?", (cat_key, itens, offset))
        jogos = await c2.fetchall()

    b = []
    for j_id, nome, preco in jogos:
        rotulo = f"R$ {preco:.2f}"
        b.append([btn(f"🔵 {nome} - {rotulo}", cb_data=f"info_{j_id}", estilo="primary")])

    total_p = max(1, (total + itens - 1) // itens)
    nav = []
    if pagina > 1:
        nav.append(btn("⬅️ Anterior", cb_data=f"cat_{cat_key}_{pagina - 1}"))
    if total_p > 1:
        nav.append(btn(f"📄 {pagina}/{total_p}", cb_data="noop"))
    if pagina < total_p:
        nav.append(btn("Próxima ➡️", cb_data=f"cat_{cat_key}_{pagina + 1}"))
    if nav:
        b.append(nav)

    b.append([btn("◀️ Voltar às Categorias", cb_data="menu_cat")])
    return InlineKeyboardMarkup(inline_keyboard=b), total

# ================= COMANDOS =================
@dp.message(Command("novojogo"))
async def cmd_novo_jogo(m: Message):
    if m.from_user.id != ADMIN_ID: return
    partes = [p.strip() for p in m.text.replace("/novojogo", "").split("|")]
    if len(partes) < 6:
        await m.answer("⚠️ Formato: `/novojogo id | Nome | cat | preco | link | desc`", parse_mode="Markdown")
        return
    j_id, nome, cat, preco_str, link, desc = partes[0].lower(), partes[1], partes[2].lower(), partes[3], partes[4], partes[5]
    if cat not in CATEGORIAS:
        await m.answer("❌ Categoria inválida.")
        return
    try: preco = float(preco_str.replace(",", "."))
    except ValueError: return
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, categoria=excluded.categoria, preco=excluded.preco, link_download=excluded.link_download, descricao=excluded.descricao", (j_id, nome, cat, preco, link, desc))
        await db.commit()
    await m.answer(f"✅ Cadastrado: **{nome}**", parse_mode="Markdown")

@dp.message(CommandStart())
async def cmd_start(m: Message):
    await m.answer(TEXTO_BOAS_VINDAS, reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_buscar(m: Message):
    termo = m.text.replace("/buscar", "").strip()
    if not termo:
        await m.answer("🔍 Envie `/buscar nome-do-jogo`", parse_mode="Markdown")
        return
    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT id, nome, preco FROM jogos WHERE nome LIKE ? LIMIT 8", (f"%{termo}%",))
        jogos = await c.fetchall()
    if not jogos:
        await m.answer("❌ Nenhum jogo encontrado.")
        return
    b = [[btn(f"🔵 {nome} - R$ {preco:.2f}", cb_data=f"info_{j_id}", estilo="primary")] for j_id, nome, preco in jogos]
    b.append([btn("◀️ Voltar ao Início", cb_data="voltar_inicio")])
    await m.answer(f"🔍 Resultados para: `{termo}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=b), parse_mode="Markdown")

# ================= NAVEGAÇÃO =================
@dp.callback_query(F.data == "menu_desbloqueios")
async def cb_menu_desbloqueios(cb: CallbackQuery):
    await cb.answer()
    texto = "🎁 **Desbloqueios Gratuitos para Xbox 360:**\nEscolha o método desejado:"
    try:
        await cb.message.edit_text(texto, reply_markup=kb_desbloqueios(), parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data == "menu_dashboards")
async def cb_menu_dashboards(cb: CallbackQuery):
    await cb.answer()
    texto = "🎁 **Dashboards Gratuitas para Xbox 360:**\nEscolha a interface para instalar:"
    try:
        await cb.message.edit_text(texto, reply_markup=kb_dashboards(), parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data == "menu_cat")
async def cb_cat(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("📂 **Categorias de Jogos:**", reply_markup=kb_categorias(), parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data.startswith("cat_"))
async def cb_jogos_cat(cb: CallbackQuery):
    partes = cb.data.split("_")
    cat_key = partes[1]
    pagina = int(partes[2])
    nome_cat = CATEGORIAS.get(cat_key, "Categoria")
    await cb.answer()
    markup, total = await kb_jogos(cat_key, pagina)
    txt = f"📂 **{nome_cat}**" if total > 0 else f"📂 **{nome_cat}**\n\n_Nenhum item cadastrado ainda nesta categoria._"
    try:
        await cb.message.edit_text(txt, reply_markup=markup, parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data.startswith("info_"))
async def cb_info(cb: CallbackQuery):
    j_id = cb.data.replace("info_", "")
    await cb.answer()
    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT nome, preco, descricao, categoria, link_download FROM jogos WHERE id = ?", (j_id,))
        jogo = await c.fetchone()
    if not jogo: return
    nome, preco, desc, cat_key, link = jogo

    if cat_key == "gratis":
        voltar_cb = "menu_desbloqueios"
    elif cat_key == "dashboards":
        voltar_cb = "menu_dashboards"
    else:
        voltar_cb = f"cat_{cat_key}_1" if cat_key in CATEGORIAS else "menu_cat"

    if preco == 0.0:
        txt = f"🎁 **{nome}** (Grátis)\n\n📝 {desc}"
        b = [
            [btn("🟢 Baixar Agora (Canal VIP)", url=link, estilo="success")],
            [btn("◀️ Voltar", cb_data=voltar_cb)]
        ]
    else:
        txt = f"🎮 **{nome}**\n💰 R$ {preco:.2f} (GOD / XEX)\n\n📝 {desc}"
        b = [
            [btn(f"🟢 Pagar R$ {preco:.2f} via Pix", cb_data=f"gerarpix_{j_id}", estilo="success")],
            [btn("◀️ Voltar à Lista", cb_data=voltar_cb)]
        ]
    try:
        await cb.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=b), parse_mode="Markdown")
    except Exception: pass

@dp.callback
