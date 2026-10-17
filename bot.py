import os, asyncio, urllib.parse, aiosqlite, mercadopago
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, InlineKeyboardButton as IKB, InlineKeyboardMarkup as IKM, Message

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "").strip()
ADMIN_ID = 1858295769

sdk = mercadopago.SDK(MP_ACCESS_TOKEN) if MP_ACCESS_TOKEN else None
bot, dp, DB_FILE = Bot(token=BOT_TOKEN), Dispatcher(), "x360_store.db"

TXT_START = (
    "🎮 **X360 TECH BR | Loja Oficial**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚡ O seu Xbox 360 no nível máximo!\n\n"
    "🟢 **Entrega Automática via Pix** (24/7)\n"
    "📦 **Formatos:** GOD e XEX prontos p/ Pendrive/HD\n"
    "🎁 **Desbloqueios e Dashboards Gratuitos**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    "👇 _Toque numa opção abaixo para começar:_"
)

CATEGORIAS = {
    "gratis": "🎁 Desbloqueios", "acao": "💥 Ação", "aventura": "🗺️ Aventura",
    "corrida": "🚗 Corrida", "luta": "🥊 Luta", "fps": "🎯 FPS", "tiro": "🔫 Tiro",
    "esportes": "⚽ Esportes", "mundo_aberto": "🌆 Mundo Aberto", "plataforma": "🧱 Plataforma",
    "terror": "🧟 Terror", "rpg": "🧙 RPG", "kinect": "🕺 Kinect"
}

def btn(t, cb=None, url=None, s="primary"):
    kw = {"text": t}
    if cb: kw["callback_data"] = cb
    if url: kw["url"] = url
    try: return IKB(**kw, style=s)
    except TypeError: return IKB(**kw)

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS jogos (id TEXT PRIMARY KEY, nome TEXT, categoria TEXT, preco REAL, link_download TEXT, descricao TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS pedidos (payment_id INTEGER PRIMARY KEY, user_id INTEGER, jogo_id TEXT, status TEXT)")
        await db.execute("DELETE FROM jogos WHERE categoria IN ('gratis', 'dashboards') OR id IN ('abadavatar', 'badavatar', 'rockband', 'dash_aurora', 'dash_nexus', 'vip_total')")
        itens = [
            ('abadavatar', 'Desbloqueio AbadAvatar', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Guia e ficheiros para desbloqueio AbadAvatar no Xbox 360.'),
            ('rockband', 'Desbloqueio Rock Band', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Ficheiros essenciais para desbloqueio Rock Band no Xbox 360.'),
            ('dash_aurora', 'Dashboard Aurora', 'dashboards', 0.0, 'https://t.me/+SEU_CANAL', 'Interface moderna com capas automáticas e title updates.'),
            ('dash_nexus', 'Dashboard Nexus', 'dashboards', 0.0, 'https://t.me/+SEU_CANAL', 'Dashboard com menus rápidos e plugins customizados.')
        ]
        await db.executemany("INSERT INTO jogos VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, descricao=excluded.descricao", itens)
        await db.commit()

def kb_inicio():
    return IKM(inline_keyboard=[
        [btn("🟢 Desbloqueios (Grátis)", cb="menu_desbloqueios", s="success")],
        [btn("🟢 Dashboards (Aurora & Nexus)", cb="menu_dashboards", s="success")],
        [btn("🔵 Catálogo de Jogos (GOD / XEX)", cb="menu_cat", s="primary")],
        [btn("🔍 Pesquisar Jogo", cb="ajuda_busca"), btn("📖 Como Instalar", cb="tutorial_inst")]
    ])

def kb_desbloqueios():
    return IKM(inline_keyboard=[
        [btn("🟢 Desbloqueio AbadAvatar", cb="info_abadavatar", s="success")],
        [btn("🟢 Desbloqueio Rock Band", cb="info_rockband", s="success")],
        [btn("◀️ Voltar ao Início", cb="voltar_inicio")]
    ])

def kb_dashboards():
    return IKM(inline_keyboard=[
        [btn("🟢 Dashboard Aurora", cb="info_dash_aurora", s="success")],
        [btn("🟢 Dashboard Nexus", cb="info_dash_nexus", s="success")],
        [btn("◀️ Voltar ao Início", cb="voltar_inicio")]
    ])

def kb_categorias():
    keys = list(CATEGORIAS.keys())[1:]
    grid = [[btn(CATEGORIAS[keys[i]], cb=f"cat_{keys[i]}_1"), btn(CATEGORIAS[keys[i+1]], cb=f"cat_{keys[i+1]}_1")] for i in range(0, len(keys)-1, 2)]
    if len(keys) % 2 != 0: grid.append([btn(CATEGORIAS[keys[-1]], cb=f"cat_{keys[-1]}_1")])
    grid.append([btn("🟢 Ver Desbloqueios", cb="menu_desbloqueios", s="success")])
    grid.append([btn("◀️ Voltar ao Início", cb="voltar_inicio")])
    return IKM(inline_keyboard=grid)

async def kb_jogos(cat_key, pag=1):
    itens, off = 6, (pag - 1) * 6
    async with aiosqlite.connect(DB_FILE) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM jogos WHERE categoria = ?", (cat_key,))
        tot = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT id, nome, preco FROM jogos WHERE categoria = ? ORDER BY nome ASC LIMIT 6 OFFSET ?", (cat_key, off))
        rows = await c2.fetchall()
    b = [[btn(f"🔵 {n} - R$ {p:.2f}", cb=f"info_{i}", s="primary")] for i, n, p in rows]
    tot_p = max(1, (tot + 5) // 6)
    nav = []
    if pag > 1: nav.append(btn("⬅️ Anterior", cb=f"cat_{cat_key}_{pag-1}"))
    if tot_p > 1: nav.append(btn(f"📄 {pag}/{tot_p}", cb="noop"))
    if pag < tot_p: nav.append(btn("Próxima ➡️", cb=f"cat_{cat_key}_{pag+1}"))
    if nav: b.append(nav)
    b.append([btn("◀️ Voltar às Categorias", cb="menu_cat")])
    return IKM(inline_keyboard=b), tot

@dp.message(Command("novojogo"))
async def cmd_novo(m: Message):
    if m.from_user.id != ADMIN_ID: return
    p = [x.strip() for x in m.text.replace("/novojogo", "").split("|")]
    if len(p) < 6: return await m.answer("⚠️ Use: `/novojogo id|Nome|cat|preco|link|desc`", parse_mode="Markdown")
    try: val = float(p[3].replace(",", "."))
    except ValueError: return
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO jogos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, categoria=excluded.categoria, preco=excluded.preco, link_download=excluded.link_download, descricao=excluded.descricao", (p[0].lower(), p[1], p[2].lower(), val, p[4], p[5]))
        await db.commit()
    await m.answer(f"✅ Cadastrado: **{p[1]}**", parse_mode="Markdown")

@dp.message(CommandStart())
async def cmd_s(m: Message): await m.answer(TXT_START, reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_b(m: Message):
    t = m.text.replace("/buscar", "").strip()
    if not t: return await m.answer("🔍 Envie `/buscar nome-do-jogo`", parse_mode="Markdown")
    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT id, nome, preco FROM jogos WHERE nome LIKE ? LIMIT 8", (f"%{t}%",))
        rows = await c.fetchall()
    if not rows: return await m.answer("❌ Nenhum jogo encontrado.")
    b = [[btn(f"🔵 {n} - R$ {p:.2f}", cb=f"info_{i}", s="primary")] for i, n, p in rows]
    b.append([btn("◀️ Voltar ao Início", cb="voltar_inicio")])
    await m.answer(f"🔍 Resultados para: `{t}`", reply_markup=IKM(inline_keyboard=b), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_desbloqueios")
async def cb_desb(cb: CallbackQuery):
    await cb.answer()
    try: await cb.message.edit_text("🎁 **Desbloqueios Gratuitos para Xbox 360:**\nEscolha o método:", reply_markup=kb_desbloqueios(), parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data == "menu_dashboards")
async def cb_dash(cb: CallbackQuery):
    await cb.answer()
    try: await cb.message.edit_text("🎁 **Dashboards Gratuitas para Xbox 360:**\nEscolha a interface:", reply_markup=kb_dashboards(), parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data == "menu_cat")
async def cb_cat(cb: CallbackQuery):
    await cb.answer()
    try: await cb.message.edit_text("📂 **Categorias de Jogos:**", reply_markup=kb_categorias(), parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data.startswith("cat_"))
async def cb_jcat(cb: CallbackQuery):
    _, cat, pag = cb.data.split("_")
    await cb.answer()
    mk, tot = await kb_jogos(cat, int(pag))
    txt = f"📂 **{CATEGORIAS.get(cat, 'Jogos')}**" if tot > 0 else f"📂 **{CATEGORIAS.get(cat, 'Jogos')}**\n
