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
    "kinect": "🕺 Kinect",
    "modificados": "🛠️ Jogos Modificados para Xbox 360",
    "servidores_furtivos": "🛰️ Servidores Furtivos"
}

class FormCadastro(StatesGroup):
    nome = State()
    categoria = State()
    preco = State()
    link = State()
    descricao = State()

def btn(t, cb=None, u=None, s=None):
    k = {"text": t}
    if cb:
        k["callback_data"] = cb
    if u:
        k["url"] = u
    # Give every inline button a green/blue style by default.
    # Explicit style arguments still take precedence.
    if s is None:
        s = "success" if "🟢" in t else "primary"
    if s in {"primary", "success"}:
        k["style"] = s
    try:
        return IKB(**k)
    except Exception as e:
        # Keep the shop available if the installed Telegram schema does not
        # support button styling, but make the fallback visible in Render logs.
        if "style" in k:
            print("AVISO: estilo de botao Telegram nao suportado pelo aiogram/schema:", repr(e))
            k.pop("style", None)
            return IKB(**k)
        raise

def slugify(text):
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '_', str(text).strip().lower()).strip('_')
    return cleaned[:25] or "jogo"

def parse_tg_link(link):
    m = re.search(r't\.me/c/(\d+)/(\d+)', link)
    if m:
        chat_id = int("-100" + m.group(1))
        msg_id = int(m.group(2))
        return chat_id, msg_id
    return None, None

async def entregar_conteudo(user_id, link, nome_jogo):
    chat_id, msg_id = parse_tg_link(link)
    if chat_id and msg_id:
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=chat_id, message_id=msg_id)
            return True
        except Exception as e:
            print("Erro copy_message:", e)
            msg_fallback = "📥 **Download:** " + str(link)
            await bot.send_message(user_id, msg_fallback, parse_mode="Markdown")
            return False
    else:
        msg_dir = "📥 **Download de " + str(nome_jogo) + ":**\n" + str(link)
        await bot.send_message(user_id, msg_dir, parse_mode="Markdown")
        return True

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS jogos (id TEXT PRIMARY KEY, nome TEXT, cat TEXT, preco REAL, link TEXT, desc TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS pedidos (pid INT PRIMARY KEY, uid INT, jid TEXT, st TEXT)")
        itens = [
            ('abadavatar', 'Desbloqueio AbadAvatar', 'gratis', 0.0, 'https://t.me/c/4434900523/2', 'Guia e ficheiros para desbloqueio AbadAvatar.'),
            ('rockband', 'Desbloqueio Rock Band', 'gratis', 0.0, 'https://t.me/c/4434900523/2', 'Ficheiros essenciais para desbloqueio Rock Band.'),
            ('dash_aurora', 'Aurora', 'dashboards', 0.0, 'https://t.me/c/4434900523/2', 'Interface moderna com capas automaticas.'),
            ('dash_nexus', 'Nexus', 'dashboards', 0.0, 'https://t.me/c/4434900523/2', 'Dashboard com menus rapidos e plugins.'),
            ('limbo', 'Limbo', 'plataforma', 4.99, 'https://t.me/c/4434900523/5', 'Jogo completo Limbo para Xbox 360 RGH/JTAG.'),
            ('crazy_taxi', 'Crazy Taxi', 'corrida', 4.99, 'https://t.me/c/4434900523/8', 'Classico Crazy Taxi pronto para pendrive.')
        ]
        # Seeds are added only when missing; never overwrite or delete catalog entries on startup.
        await db.executemany("INSERT OR IGNORE INTO jogos VALUES (?,?,?,?,?,?)", itens)
        # Aurora and Nexus were accidentally seeded with the same destination.
        # Disable only the known-wrong Aurora URL until its real post link is supplied.
        await db.execute(
            "UPDATE jogos SET link = '' WHERE id = 'dash_aurora' AND link = 'https://t.me/c/4434900523/2'"
        )
        await db.commit()

def kb_inicio():
    return IKM(inline_keyboard=[
        [btn("🟢 Desbloqueios (Gratis)", cb="menu_desb", s="success")],
        [btn("🟢 Dashboards (Aurora & Nexus)", cb="menu_dash", s="success")],
        [btn("🔵 Catalogo de Jogos (GOD / XEX)", cb="menu_cat", s="primary")],
        [btn("🛠️ Jogos Modificados para Xbox 360", cb="c_modificados_1", s="primary")],
        [btn("🛰️ Servidores Furtivos", cb="c_servidores_furtivos_1", s="success")],
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
        g.append([btn(CATS[k[i]], cb="c_" + k[i] + "_1"), btn(CATS[k[i+1]], cb="c_" + k[i+1] + "_1")])
    if len(k) % 2:
        g.append([btn(CATS[k[-1]], cb="c_" + k[-1] + "_1")])
    g.append([btn("🟢 Ver Desbloqueios", cb="menu_desb", s="success")])
    g.append([btn("◀️ Voltar ao Inicio", cb="voltar_ini")])
    return IKM(inline_keyboard=g)

def kb_escolher_categoria():
    k = list(CATS.keys())
    botoes = []
    for i in range(0, len(k)-1, 2):
        botoes.append([btn(CATS[k[i]], cb="selcat_" + k[i]), btn(CATS[k[i+1]], cb="selcat_" + k[i+1])])
    if len(k) % 2:
        botoes.append([btn(CATS[k[-1]], cb="selcat_" + k[-1])])
    botoes.append([btn("❌ Cancelar", cb="cancelar_fsm")])
    return IKM(inline_keyboard=botoes)

async def kb_lista(ck, pg=1):
    off = (pg - 1) * 6
    async with aiosqlite.connect(DB) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM jogos WHERE cat = ?", (ck,))
        tot = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT id, nome, preco FROM jogos WHERE cat = ? ORDER BY nome ASC LIMIT 6 OFFSET ?", (ck, off))
        rows = await c2.fetchall()
    b = []
    for r in rows:
        jid_item = str(r[0])
        nome_item = str(r[1])
        preco_item = float(r[2])
        label_btn = "🔵 " + nome_item + " - R$ " + f"{preco_item:.2f}"
        b.append([btn(label_btn, cb="info_" + jid_item, s="primary")])
    tot_p = max(1, (tot + 5) // 6)
    nav = []
    if pg > 1:
        nav.append(btn("⬅️ Anterior", cb="c_" + str(ck) + "_" + str(pg-1)))
    if tot_p > 1:
        nav.append(btn("📄 " + str(pg) + "/" + str(tot_p), cb="noop"))
    if pg < tot_p:
        nav.append(btn("Proxima ➡️", cb="c_" + str(ck) + "_" + str(pg+1)))
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

@dp.message(Command("stats"))
@dp.message(Command("total"))
async def cmd_estatisticas(m):
    if m.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT cat FROM jogos WHERE preco > 0")
        linhas = await res.fetchall()
    tot = len(linhas)
    cont = {}
    for r in linhas:
        c = r[0]
        cont[c] = cont.get(c, 0) + 1
    t = "📊 **Estoque:** " + str(tot) + " jogos pagos\n━━━━━━━━━━━━━━━━━━━━━\n"
    for k, v in cont.items():
        nom = CATS.get(k, k)
        t += "• **" + str(nom) + ":** " + str(v) + "\n"
    if not cont:
        t += "_Nenhum jogo pago cadastrado._\n"
    t += "━━━━━━━━━━━━━━━━━━━━━"
    await m.answer(t, parse_mode="Markdown")

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
    await m.answer("🎮 **" + nome + "**\n\nEscolha a categoria:", reply_markup=kb_escolher_categoria(), parse_mode="Markdown")

@dp.callback_query(FormCadastro.categoria, F.data.startswith("selcat_"))
async def processa_categoria(c, state: FSMContext):
    cat = c.data.replace("selcat_", "")
    await state.update_data(cat=cat)
    await state.set_state(FormCadastro.preco)
    await c.answer()
    cancel_kb = IKM(inline_keyboard=[[btn("❌ Cancelar", cb="cancelar_fsm")]])
    nome_cat = str(CATS.get(cat, cat))
    await safe_edit(c, "📂 Categoria: **" + nome_cat + "**\n\nEnvie o preco (ex: `10.00`):", cancel_kb)

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
    await m.answer("🔗 Envie o link do ficheiro:", reply_markup=cancel_kb, parse_mode="Markdown")

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
    
    nm = str(data.get('nome', ''))
    ct = str(data.get('cat', ''))
    pr = float(data.get('preco', 0.0))
    cat_nome = str(CATS.get(ct, ct))
    res = "✅ **Jogo Cadastrado!**\n\n🎮 " + nm + "\n📂 " + cat_nome + "\n💰 R$ " + f"{pr:.2f}"
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
    link = "https://t.me/c/4434900523/2"
    if chat_id and msg_id:
        c_str = str(chat_id).replace("-100", "").replace("-", "")
        link = "https://t.me/c/" + c_str + "/" + str(msg_id)
    jid = slugify(nome)
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO jogos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
            (jid, nome, cat, val, link, desc)
        )
        await db.commit()
    await m.answer("⚡ **Cadastrado:** " + str(nome) + " (R$ " + f"{val:.2f}" + ")", reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(Command("novojogo"))
async def cmd_novo(m):
    if m.from_user.id != ADMIN_ID:
        return
    p = [x.strip() for x in m.text.replace("/novojogo", "").split("|")]
    if len(p) < 6:
        return await m.answer("Use: `/novojogo id | Nome | cat | preco | link | desc`", parse_mode="Markdown")
    try:
        val = float(p[3].replace(",", "."))
    except Exception:
        return await m.answer("⚠️ Preço inválido.")
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO jogos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
            (p[0].lower(), p[1], p[2].lower(), val, p[4], p[5])
        )
        await db.commit()
    await m.answer("✅ Cadastrado: **" + str(p[1]) + "**", parse_mode="Markdown")

@dp.message(CommandStart())
async def cmd_st(m):
    try:
        await m.delete()
    except Exception:
        pass
    await bot.send_chat_action(chat_id=m.chat.id, action="typing")
    await asyncio.sleep(0.3)
    await m.answer(TXT_INI, reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_bs(m):
    t = m.text.replace("/buscar", "").strip()
    if not t:
        return await m.answer("Envie: `/buscar nome-do-jogo`", parse_mode="Markdown")
    async with aiosqlite.connect(DB) as db:
        c = await db.execute("SELECT id, nome, preco FROM jogos WHERE nome LIKE ? LIMIT 8", ("%" + t + "%",))
        rows = await c.fetchall()
    if not rows:
        return await m.answer("Nenhum jogo encontrado.")
    b = []
    for r in rows:
        jid_item = str(r[0])
        nome_item = str(r[1])
        preco_item = float(r[2])
        label_btn = "🔵 " + nome_item + " - R$ " + f"{preco_item:.2f}"
        b.append([btn(label_btn, cb="info_" + jid_item, s="primary")])
    b.append([btn("◀️ Voltar ao Inicio", cb="voltar_ini")])
    await m.answer("Resultados para: `" + str(t) + "`", reply_markup=IKM(inline_keyboard=b), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_desb")
async def cb_db(c):
    await c.answer()
    await safe_edit(c, "🎁 **Desbloqueios Gratuitos:**\nEscolha o metodo:", kb_desb())

@dp.callback_query(F.data == "menu_dash")
async def cb_dh(c):
    await c.answer()
    await safe_edit(c, "🎁 **Dashboards Gratuitas:**\nEscolha a interface:", kb_dash())

@dp.callback_query(F.data == "menu_cat")
async def cb_ct(c):
    await c.answer()
    await safe_edit(c, "📂 **Categorias de Jogos:**", kb_categorias())

@dp.callback_query(F.data.regexp(r"^c_.+_\d+$"))
async def cb_jc(c):
    # Category names may contain underscores (for example, mundo_aberto).
    match = re.fullmatch(r"c_(.+)_(\d+)", c.data)
    if not match:
        await c.answer("Categoria invalida.", show_alert=True)
        return
    ck, pg = match.group(1), int(match.group(2))
    await c.answer()
    mk, tot = await kb_lista(ck, pg)
    nom = CATS.get(ck, "Jogos")
    t = "📂 **" + str(nom) + "**" if tot > 0 else "📂 **" + str(nom) + "**\n\n_Vazio por enquanto._"
    await safe_edit(c, t, mk)

@dp.callback_query(F.data.startswith("info_"))
async def cb_in(c):
    jid = c.data.replace("info_", "")
    await c.answer()
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, preco, desc, cat, link FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, p, d, ck, link = row
    v = "menu_desb" if ck == "gratis" else ("menu_dash" if ck == "dashboards" else "c_" + str(ck) + "_1")
    if p == 0.0:
        tx = "🎁 **" + str(n) + "** (Gratis)\n\n📝 " + str(d)
        b = [[btn("🟢 Receber Ficheiro Agora", cb="getfree_" + str(jid), s="success")], [btn("◀️ Voltar", cb=v)]]
    else:
        tx = "🎮 **" + str(n) + "**\n💰 R$ " + f"{p:.2f}" + " (GOD / XEX)\n\n📝 " + str(d)
        b = [[btn("🟢 Pagar R$ " + f"{p:.2f}" + " via Pix", cb="pix_" + str(jid), s="success")], [btn("◀️ Voltar", cb=v)]]
    await safe_edit(c, tx, IKM(inline_keyboard=b))

@dp.callback_query(F.data.startswith("getfree_"))
async def cb_getfree(c):
    jid = c.data.replace("getfree_", "")
    await c.answer("A enviar ficheiro...")
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, link FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, link = row
    if not link:
        return await c.message.answer(
            "⚠️ O link deste conteúdo ainda está sendo corrigido. Nenhum arquivo foi enviado. Tente novamente mais tarde."
        )
    await c.message.answer("📦 A preparar a entrega de: **" + str(n) + "**...")
    await entregar_conteudo(c.from_user.id, link, n)

@dp.callback_query(F.data.startswith("pix_"))
async def cb_px(c):
    jid = c.data.replace("pix_", "", 1)
    await c.answer("A gerar Pix...")
    if not sdk:
        return await c.message.answer("❌ Pagamento indisponivel no momento. Tente novamente mais tarde.")
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, preco FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, pr = row
    await c.message.edit_text("⏳ A ligar ao Mercado Pago...")
    pdata = {
        "transaction_amount": float(pr),
        "description": "X360 - " + str(n),
        "payment_method_id": "pix",
        "payer": {"email": "c" + str(c.from_user.id) + "@gmail.com", "first_name": c.from_user.first_name or "Gamer"}
    }
    try:
        p = sdk.payment().create(pdata).get("response", {})
        pid, px = p["id"], p["point_of_interaction"]["transaction_data"]["qr_code"]
    except Exception as e:
        return await c.message.edit_text("❌ Erro Pix: " + str(e))
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO pedidos VALUES (?, ?, ?, 'pending')", (pid, c.from_user.id, jid))
        await db.commit()
    qr = "https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=" + urllib.parse.quote(px)
    kb = IKM(inline_keyboard=[[btn("🟢 Ja Paguei (Liberar Download)", cb="chk_" + str(pid), s="success")], [btn("◀️ Cancelar", cb="voltar_ini")]])
    await c.message.delete()
    caption_txt = "🎮 **" + str(n) + "**\n💰 R$ " + f"{pr:.2f}" + "\n\n`" + str(px) + "`"
    await c.message.answer_photo(photo=qr, caption=caption_txt, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("chk_"))
async def cb_ck(c):
    raw_pid = c.data.replace("chk_", "", 1)
    try:
        pid = int(raw_pid)
    except ValueError:
        return await c.answer("Pedido invalido.", show_alert=True)
    if not sdk:
        return await c.answer("Pagamento indisponivel no momento.", show_alert=True)
    try:
        resp = sdk.payment().get(pid).get("response", {})
        status_pagamento = resp.get("status")
    except Exception:
        return await c.answer("Erro ao consultar Mercado Pago. Tente novamente.", show_alert=True)
    if status_pagamento != "approved":
        return await c.answer("⏳ Aguardando compensacao Pix...", show_alert=True)
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT uid, jid, st FROM pedidos WHERE pid = ?", (pid,))
        ped = await res.fetchone()
        if not ped:
            return await c.answer("Pedido nao encontrado.", show_alert=True)
        owner_id, jid, status_pedido = ped
        if int(owner_id) != int(c.from_user.id):
            return await c.answer("Este pedido pertence a outro usuario.", show_alert=True)
        if status_pedido == "delivered":
            return await c.answer("Este pedido ja foi entregue.", show_alert=True)
        r2 = await db.execute("SELECT nome, link FROM jogos WHERE id = ?", (jid,))
        jogo = await r2.fetchone()
        if not jogo:
            return await c.answer("Produto nao encontrado. Contate o administrador.", show_alert=True)
        n, l = jogo
    await c.answer("Pagamento confirmado; enviando produto...")
    await c.message.answer("🎉 **PAGAMENTO CONFIRMADO!**\n\n🎮 A entregar: **" + str(n) + "**...", parse_mode="Markdown")
    try:
        entregue = await entregar_conteudo(c.from_user.id, l, n)
    except Exception as e:
        print("Falha na entrega do pedido", pid, ":", e)
        entregue = False
    if entregue:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE pedidos SET st = 'delivered' WHERE pid = ? AND uid = ?", (pid, c.from_user.id))
            await db.commit()
        await c.message.answer("✅ Entrega concluida. Guarde esta conversa para consultar o produto.")
    else:
        await c.message.answer("⚠️ O pagamento foi confirmado, mas o envio automatico falhou. Seu pedido nao foi marcado como entregue. Contate o administrador para concluir a entrega.")

@dp.callback_query(F.data == "voltar_ini")
async def cb_vi(c):
    await c.answer()
    await safe_edit(c, TXT_INI, kb_inicio())

@dp.callback_query(F.data == "ajuda_b")
async def cb_ab(c):
    await c.answer()
    await safe_edit(c, "🔍 **Como Pesquisar:**\nEnvie `/buscar` e o nome.\n\nExemplo: `/buscar limbo`", IKM(inline_keyboard=[[btn("◀️ Voltar", cb="voltar_ini")]]))

@dp.callback_query(F.data == "tut_inst")
async def cb_ti(c):
    await c.answer()
    t = "📖 **Tutorial Rapido:**\n\n1. Pendrive em FAT32.\n2. **GOD:** em `Content\\0000000000000000`\n3. **XEX:** em `Games`\n4. Abra a Aurora ou Nexus!"
    await safe_edit(c, t, IKM(inline_keyboard=[[btn("◀️ Voltar", cb="voltar_ini")]]))

@dp.callback_query(F.data == "noop")
async def cb_np(c):
    await c.answer()

async def ping(request):
    return web.Response(text="Online!")

def make_web_app():
    app = web.Application()
    app.router.add_get("/", ping)
    app.router.add_get("/healthz", ping)
    return app

async def main():
    await init_db()
    app = make_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print("🚀 Web server ativo na porta " + str(PORT) + "!")
    print("🚀 Polling do Bot iniciado!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

