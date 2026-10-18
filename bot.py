import os, asyncio, urllib.parse, aiosqlite, mercadopago, re
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup as IKM

TOKEN = os.getenv("BOT_TOKEN", "").strip()
MP_KEY = os.getenv("MP_ACCESS_TOKEN", "").strip()
PORT = int(os.getenv("PORT", 10000))
ADMIN_ID = 1858295769

sdk = mercadopago.SDK(MP_KEY) if MP_KEY else None
bot = Bot(token=TOKEN)
dp = Dispatcher()
DB = "x360_store.db"

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
    "kinect": "🕺 Kinect"
}

class FormCadastro(StatesGroup):
    nome = State()
    categoria = State()
    preco = State()
    link = State()
    descricao = State()

def btn(t, cb=None, u=None, s="primary"):
    k = {"text": t}
    if cb:
        k["callback_data"] = cb
    if u:
        k["url"] = u
    try:
        return IKB(**k, style=s)
    except:
        return IKB(**k)

def slugify(text):
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '_', str(text).strip().lower()).strip('_')
    return cleaned[:25] or "jogo"

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS jogos (id TEXT PRIMARY KEY, nome TEXT, cat TEXT, preco REAL, link TEXT, desc TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS pedidos (pid INT PRIMARY KEY, uid INT, jid TEXT, st TEXT)")
        await db.execute("DELETE FROM jogos WHERE cat IN ('gratis','dashboards') OR id IN ('abadavatar','badavatar','rockband','dash_aurora','dash_nexus') OR nome LIKE '%http%'")
        itens = [
            ('abadavatar', 'Desbloqueio AbadAvatar', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Guia e ficheiros para desbloqueio AbadAvatar.'),
            ('rockband', 'Desbloqueio Rock Band', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Ficheiros essenciais para desbloqueio Rock Band.'),
            ('dash_aurora', 'Aurora', 'dashboards', 0.0, 'https://t.me/+SEU_CANAL', 'Interface moderna com capas automaticas.'),
            ('dash_nexus', 'Nexus', 'dashboards', 0.0, 'https://t.me/c/4434900523/2', 'Dashboard com menus rapidos e plugins.')
        ]
        await db.executemany("INSERT INTO jogos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, link=excluded.link, desc=excluded.desc, preco=excluded.preco", itens)
        await db.commit()

def kb_inicio():
    return IKM(inline_keyboard=[
        [btn("🟢 Desbloqueios (Gratis)", cb="menu_desb", s="success")],
        [btn("🟢 Dashboards (Aurora & Nexus)", cb="menu_dash", s="success")],
        [btn("🔵 Catalogo de Jogos (GOD / XEX)", cb="menu_cat", s="primary")],
        [btn("🔍 Pesquisar Jogo", cb="ajuda_b"), btn("📖 Como Instalar", cb="tut_inst")]
    ])

def kb_desb():
    return IKM(inline_keyboard=[
        [btn("🟢 Desbloqueio AbadAvatar", cb="info_abadavatar", s="success")],
        [btn("🟢 Desbloqueio Rock Band", cb="info_rockband", s="success")],
        [btn("◀️ Voltar ao Inicio", cb="voltar_ini")]
    ])

def kb_dash():
    return IKM(inline_keyboard=[
        [btn("🟢 Aurora", cb="info_dash_aurora", s="success")],
        [btn("🟢 Nexus", cb="info_dash_nexus", s="success")],
        [btn("◀️ Voltar ao Inicio", cb="voltar_ini")]
    ])

def kb_categorias():
    k = list(CATS.keys())
    g = []
    for i in range(0, len(k)-1, 2):
        g.append([btn(CATS[k[i]], cb=f"c_{k[i]}_1"), btn(CATS[k[i+1]], cb=f"c_{k[i+1]}_1")])
    if len(k) % 2:
        g.append([btn(CATS[k[-1]], cb=f"c_{k[-1]}_1")])
    g.append([btn("🟢 Ver Desbloqueios", cb="menu_desb", s="success")])
    g.append([btn("◀️ Voltar ao Inicio", cb="voltar_ini")])
    return IKM(inline_keyboard=g)

def kb_escolher_categoria():
    k = list(CATS.keys())
    botoes = []
    for i in range(0, len(k)-1, 2):
        botoes.append([btn(CATS[k[i]], cb=f"selcat_{k[i]}"), btn(CATS[k[i+1]], cb=f"selcat_{k[i+1]}")])
    if len(k) % 2:
        botoes.append([btn(CATS[k[-1]], cb=f"selcat_{k[-1]}")])
    botoes.append([btn("❌ Cancelar", cb="cancelar_fsm")])
    return IKM(inline_keyboard=botoes)

async def kb_lista(ck, pg=1):
    off = (pg - 1) * 6
    async with aiosqlite.connect(DB) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM jogos WHERE cat = ?", (ck,))
        tot = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT id, nome, preco FROM jogos WHERE cat = ? ORDER BY nome ASC LIMIT 6 OFFSET ?", (ck, off))
        rows = await c2.fetchall()
    b = [[btn(f"🔵 {n} - R$ {p:.2f}", cb=f"info_{i}", s="primary")] for i, n, p in rows]
    tot_p = max(1, (tot + 5) // 6)
    nav = []
    if pg > 1:
        nav.append(btn("⬅️ Anterior", cb=f"c_{ck}_{pg-1}"))
    if tot_p > 1:
        nav.append(btn(f"📄 {pg}/{tot_p}", cb="noop"))
    if pg < tot_p:
        nav.append(btn("Proxima ➡️", cb=f"c_{ck}_{pg+1}"))
    if nav:
        b.append(nav)
    b.append([btn("◀️ Voltar as Categorias", cb="menu_cat")])
    return IKM(inline_keyboard=b), tot

async def safe_edit(cb, text, markup):
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        try:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass

@dp.message(Command("cadastrar"))
async def cmd_iniciar_cadastro(m, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await state.set_state(FormCadastro.nome)
    cancel_kb = IKM(inline_keyboard=[[btn("❌ Cancelar", cb="cancelar_fsm")]])
    await m.answer("📝 **Cadastro (1/5):** Qual o nome do jogo?", reply_markup=cancel_kb, parse_mode="Markdown")

@dp.callback_query(F.data == "cancelar_fsm")
async def cb_cancela_fsm(c, state: FSMContext):
    await state.clear()
    await c.answer("Cancelado.")
    await safe_edit(c, "❌ Cadastro cancelado.", kb_inicio())

@dp.message(FormCadastro.nome)
async def processa_nome(m, state: FSMContext):
    nome = m.text.strip()
    await state.update_data(nome=nome, jid=slugify(nome))
    await state.set_state(FormCadastro.categoria)
    await m.answer(f"🎮 **{nome}**\n\nEscolha a categoria:", reply_markup=kb_escolher_categoria(), parse_mode="Markdown")

@dp.callback_query(FormCadastro.categoria, F.data.startswith("selcat_"))
async def processa_categoria(c, state: FSMContext):
    cat = c.data.replace("selcat_", "")
    await state.update_data(cat=cat)
    await state.set_state(FormCadastro.preco)
    await c.answer()
    cancel_kb = IKM(inline_keyboard=[[btn("❌ Cancelar", cb="cancelar_fsm")]])
    await safe_edit(c, f"📂 Categoria: **{CATS.get(cat, cat)}**\n\nEnvie o preco (ex: `10.00`):", cancel_kb)

@dp.message(FormCadastro.preco)
async def processa_preco(m, state: FSMContext):
    txt = m.text.replace(",", ".").strip()
    try:
        val = float(txt)
    except ValueError:
        return await m.answer("⚠️ Envie um numero valido (ex: `10.00`):")
    await state.update_data(preco=val)
    await state.set_state(FormCadastro.link)
    cancel_kb = IKM(inline_keyboard=[[btn("❌ Cancelar", cb="cancelar_fsm")]])
    await m.answer("🔗 Envie o link de download:", reply_markup=cancel_kb, parse_mode="Markdown")

@dp.message(FormCadastro.link)
async def processa_link(m, state: FSMContext):
    link = m.text.strip()
    if not (link.startswith("http://") or link.startswith("https://") or link.startswith("tg://")):
        return await m.answer("⚠️ Link invalido. Comece com `https://`:")
    await state.update_data(link=link)
    await state.set_state(FormCadastro.descricao)
    cancel_kb = IKM(inline_keyboard=[[btn("❌ Cancelar", cb="cancelar_fsm")]])
    await m.answer("📝 Envie uma descricao curta:", reply_markup=cancel_kb, parse_mode="Markdown")

@dp.message(FormCadastro.descricao)
async def processa_desc(m, state: FSMContext):
    desc = m.text.strip()
    data = await state.get_data()
    await state.clear()
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO jogos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
            (data['jid'], data['nome'], data['cat'], data['preco'], data['link'], desc)
        )
        await db.commit()
    res = f"✅ **Jogo Cadastrado!**\n\n🎮 {data['nome']}\n📂 {CATS.get(data['cat'], data['cat'])}\n💰 R$ {data['preco']:.2f}"
    await m.answer(res, reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(F.forward_origin)
async def processa_encaminhado(m):
    if m.from_user.id != ADMIN_ID:
        return
    legenda = (m.caption or m.text or "").strip()
    partes = [p.strip() for p in legenda.split("|")]
    if len(partes) < 4:
        return await m.answer("💡 Legenda: `Nome | categoria | preco | descricao`")
    nome, cat_raw, preco_raw, desc = partes[0], partes[1].lower(), partes[2], partes[3]
    try:
        val = float(preco_raw.replace(",", "."))
    except ValueError:
        return await m.answer("⚠️ Preco invalido na legenda.")
    cat = cat_raw if cat_raw in CATS else "acao"
    origin = m.forward_origin
    chat_id = getattr(getattr(origin, "chat", None), "id", None)
    msg_id = getattr(origin, "message_id", None)
    link = "https://t.me/+SEU_CANAL"
    if chat_id and msg_id:
        c_str = str(chat_id).replace("-100", "").replace("-", "")
        link = f"https://t.me/c/{c_str}/{msg_id}"
    jid = slugify(nome)
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO jogos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
            (jid, nome, cat, val, link, desc)
        )
        await db.commit()
    await m.answer(f"⚡ **Cadastrado:** {nome} (R$ {val:.2f})", reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(Command("novojogo"))
async def cmd_novo(m):
    if m.from_user.id != ADMIN_ID:
        return
    p = [x.strip() for x in m.text.replace("/novojogo", "").split("|")]
    if len(p) < 6:
        return await m.answer("Use: `/novojogo id | Nome | cat | preco | link | desc`", parse_mode="Markdown")
    try:
        val = float(p[3].replace(",", "."))
    except:
        return
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO jogos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
            (p[0].lower(), p[1], p[2].lower(), val, p[4], p[5])
        )
        await db.commit()
    await m.answer(f"✅ Cadastrado: **{p[1]}**", parse_mode="Markdown")

@dp.message(CommandStart())
async def cmd_st(m):
    try:
        await m.delete()
    except Exception:
        pass
    await m.answer(TXT_INI, reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_bs(m):
    t = m.text.replace("/buscar", "").strip()
    if not t:
        return await m.answer("Envie: `/buscar nome-do-jogo`", parse_mode="Markdown")
    async with aiosqlite.connect(DB) as db:
        c = await db.execute("SELECT id, nome, preco FROM jogos WHERE nome LIKE ? LIMIT 8", (f"%{
