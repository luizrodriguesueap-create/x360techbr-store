import os, asyncio, urllib.parse, aiosqlite, mercadopago, re
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup as IKM, WebAppInfo, FSInputFile
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.getenv("BOT_TOKEN", "").strip()
MP_KEY = os.getenv("MP_ACCESS_TOKEN", "").strip()
PORT = int(os.getenv("PORT", 10000))
ADMIN_ID = 1858295769

sdk = mercadopago.SDK(MP_KEY) if MP_KEY else None
bot = Bot(token=TOKEN)
dp = Dispatcher()
DB = "x360_store.db"
BANNER_PATH = "x360_banner.png"

def criar_banner():
    """Cria localmente um banner PNG da loja, sem depender de links externos."""
    if os.path.exists(BANNER_PATH):
        return
    largura, altura = 1200, 675
    img = Image.new("RGB", (largura, altura), "#07110d")
    draw = ImageDraw.Draw(img)

    # Gradiente escuro com brilho verde discreto.
    for y in range(altura):
        t = y / max(1, altura - 1)
        cor = (int(5 + 2*t), int(19 + 12*t), int(13 + 5*t))
        draw.line((0, y, largura, y), fill=cor)
    draw.ellipse((650, -180, 1280, 450), outline="#164c31", width=5)
    draw.ellipse((700, -130, 1230, 400), outline="#103b27", width=3)
    draw.ellipse((770, 50, 1160, 440), outline="#0e2d20", width=2)
    draw.rounded_rectangle((42, 42, largura-42, altura-42), radius=34, outline="#2c9d5e", width=3)

    # Ícone de controle estilizado à direita.
    draw.rounded_rectangle((760, 235, 1085, 425), radius=78, fill="#10271c", outline="#43f58a", width=5)
    draw.rounded_rectangle((795, 278, 895, 378), radius=18, fill="#0a1710", outline="#246b42", width=3)
    draw.rectangle((838, 298, 852, 357), fill="#5cff98")
    draw.rectangle((815, 320, 875, 334), fill="#5cff98")
    draw.ellipse((965, 285, 1002, 322), fill="#46f58a")
    draw.ellipse((1012, 328, 1049, 365), fill="#46f58a")
    draw.ellipse((966, 350, 1003, 387), fill="#1b8d50")
    draw.ellipse((1012, 282, 1049, 319), fill="#1b8d50")
    draw.arc((800, 270, 1045, 410), 195, 345, fill="#6dffa7", width=3)

    try:
        fonte_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 67)
        fonte_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 27)
        fonte_tag = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except OSError:
        fonte_titulo = fonte_sub = fonte_tag = ImageFont.load_default()

    draw.rounded_rectangle((85, 110, 365, 153), radius=20, fill="#123c27", outline="#2a9e5b", width=2)
    draw.text((108, 120), "SUA CENTRAL GAMER", font=fonte_tag, fill="#8affb4")
    draw.text((82, 190), "XBOX 360", font=fonte_titulo, fill="#f4fff8", stroke_width=1, stroke_fill="#0a2416")
    draw.text((82, 270), "STORE", font=fonte_titulo, fill="#45f58b", stroke_width=1, stroke_fill="#123c27")
    draw.line((86, 375, 600, 375), fill="#38d978", width=4)
    draw.text((86, 405), "JOGOS  •  CONTEÚDOS  •  FERRAMENTAS", font=fonte_sub, fill="#c4d9cc")
    draw.text((86, 510), "GOD / XEX  •  CATÁLOGO NO TELEGRAM", font=fonte_tag, fill="#6cae87")
    img.save(BANNER_PATH, format="PNG", optimize=True)

TXT_INI = "🟢 **XBOX 360 STORE**\n━━━━━━━━━━━━━━━━━━\n🎮 _Sua central gamer no Telegram_\n\nEscolha uma opção para explorar o catálogo."

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

def btn(t, cb=None, u=None, s=None, w=None):
    kwargs = {"text": t}
    if cb:
        kwargs["callback_data"] = cb
    elif w:
        kwargs["web_app"] = WebAppInfo(url=w)
    else:
        kwargs["url"] = u
    if s:
        try:
            return IKB(**kwargs, style=s)
        except (TypeError, ValueError):
            pass
    return IKB(**kwargs)

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
            print(f"Erro ao copiar: {e}")
            await bot.send_message(user_id, f"📥 **Download:** {link}", parse_mode="Markdown")
            return False
    else:
        await bot.send_message(user_id, f"📥 **Download de {nome_jogo}:**\n{link}", parse_mode="Markdown")
        return True

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS jogos (id TEXT PRIMARY KEY, nome TEXT, cat TEXT, preco REAL, link TEXT, desc TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS pedidos (pid INT PRIMARY KEY, uid INT, jid TEXT, st TEXT)")
        # Não apagar registros do catálogo durante a inicialização.
        itens = [
            ('abadavatar', 'Desbloqueio AbadAvatar', 'gratis', 0.0, '', 'Guia e ficheiros para desbloqueio AbadAvatar.'),
            ('rockband', 'Desbloqueio Rock Band', 'gratis', 0.0, '', 'Ficheiros essenciais para desbloqueio Rock Band.'),
            ('dash_aurora', 'Aurora', 'dashboards', 0.0, '', 'Interface moderna com capas automaticas.'),
            ('dash_nexus', 'Nexus', 'dashboards', 0.0, '', 'Dashboard com menus rapidos e plugins.')
        ]
        await db.executemany("INSERT INTO jogos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, link=excluded.link, desc=excluded.desc, preco=excluded.preco", itens)
        await db.commit()

def kb_inicio():
    # Grade 2x2 para as quatro ações principais, mais tutorial numa linha discreta.
    return IKM(inline_keyboard=[
        [btn("🎮 Jogos", cb="menu_cat", s="primary"),
         btn("🎁 Gratuitos", cb="menu_desb", s="success")],
        [btn("🧩 Dashboards", cb="menu_dash", s="success"),
         btn("🔎 Buscar", cb="ajuda_b")],
        [btn("📘 Tutorial de instalação", cb="tut_inst")],
    ])

def kb_desb():
    return IKM(inline_keyboard=[
        [btn("🟢 Desbloqueio AbadAvatar", cb="info_abadavatar")],
        [btn("🟢 Desbloqueio Rock Band", cb="info_rockband")],
        [btn("◀️ Voltar ao Inicio", cb="voltar_ini")]
    ])

def kb_dash():
    return IKM(inline_keyboard=[
        [btn("🟢 Aurora", cb="info_dash_aurora")],
        [btn("🟢 Nexus", cb="info_dash_nexus")],
        [btn("◀️ Voltar ao Inicio", cb="voltar_ini")]
    ])

def kb_categorias():
    k = list(CATS.keys())
    g = []
    for i in range(0, len(k)-1, 2):
        g.append([btn(CATS[k[i]], cb=f"c_{k[i]}_1"), btn(CATS[k[i+1]], cb=f"c_{k[i+1]}_1")])
    if len(k) % 2:
        g.append([btn(CATS[k[-1]], cb=f"c_{k[-1]}_1")])
    g.append([btn("🟢 Ver Desbloqueios", cb="menu_desb")])
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
    b = [[btn(f"🔵 {n} - R$ {p:.2f}", cb=f"info_{i}")] for i, n, p in rows]
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
    # Se o menu tem banner, altera a legenda e preserva a imagem; se não, edita o texto.
    try:
        if cb.message.photo:
            await cb.message.edit_caption(caption=text, reply_markup=markup, parse_mode="Markdown")
        else:
            await cb.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
        return
    except Exception as e:
        print(f"Não foi possível editar a mensagem do menu: {e}")
    try:
        await cb.message.delete()
    except Exception as e:
        print(f"Não foi possível apagar a mensagem anterior: {e}")
    try:
        await cb.message.answer(text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Não foi possível enviar o novo menu: {e}")

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
    t = f"📊 **Estoque:** {tot} jogos pagos\n━━━━━━━━━━━━━━━━━━━━━\n"
    for k, v in cont.items():
        nom = CATS.get(k, k)
        t += f"• **{nom}:** {v}\n"
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
    link = ""
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
    except Exception:
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
    criar_banner()
    await m.answer_photo(photo=FSInputFile(BANNER_PATH), caption=TXT_INI, reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_bs(m):
    t = m.text.replace("/buscar", "").strip()
    if not t:
        return await m.answer("Envie: `/buscar nome-do-jogo`", parse_mode="Markdown")
    async with aiosqlite.connect(DB) as db:
        c = await db.execute("SELECT id, nome, preco FROM jogos WHERE nome LIKE ? LIMIT 8", (f"%{t}%",))
        rows = await c.fetchall()
    if not rows:
        return await m.answer("Nenhum jogo encontrado.")
    b = [[btn(f"🔵 {n} - R$ {p:.2f}", cb=f"info_{i}")] for i, n, p in rows]
    b.append([btn("◀️ Voltar ao Inicio", cb="voltar_ini")])
    await m.answer(f"Resultados para: `{t}`", reply_markup=IKM(inline_keyboard=b), parse_mode="Markdown")

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

@dp.callback_query(F.data.startswith("c_"))
async def cb_jc(c):
    # Categorias podem conter underscores, por exemplo "mundo_aberto".
    partes = c.data.split("_")
    pg = int(partes[-1])
    ck = "_".join(partes[1:-1])
    await c.answer()
    mk, tot = await kb_lista(ck, pg)
    nom = CATS.get(ck, "Jogos")
    t = f"📂 **{nom}**" if tot > 0 else f"📂 **{nom}**\n\n_Vazio por enquanto._"
    await safe_edit(c, t, mk)

@dp.callback_query(F.data.startswith("info_"))
async def cb_in(c):
    jid = c.data.replace("info_", "")
    if jid in ("dash_aurora", "dash_nexus"):
        nome = "Aurora" if jid == "dash_aurora" else "Nexus"
        await c.answer(f"O link do {nome} está temporariamente removido. Nenhum arquivo foi enviado.", show_alert=True)
        return
    await c.answer()
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, preco, desc, cat, link FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, p, d, ck, link = row
    v = "menu_desb" if ck == "gratis" else ("menu_dash" if ck == "dashboards" else f"c_{ck}_1")
    if p == 0.0:
        tx = f"🎁 **{n}** (Gratis)\n\n📝 {d}"
        b = [[btn("🟢 Receber Ficheiro Agora", cb=f"getfree_{jid}")], [btn("◀️ Voltar", cb=v)]]
    else:
        tx = f"🎮 **{n}**\n💰 R$ {p:.2f} (GOD / XEX)\n\n📝 {d}"
        b = [[btn(f"🟢 Pagar R$ {p:.2f} via Pix", cb=f"pix_{jid}")], [btn("◀️ Voltar", cb=v)]]
    await safe_edit(c, tx, IKM(inline_keyboard=b))

@dp.callback_query(F.data.startswith("getfree_"))
async def cb_getfree(c):
    jid = c.data.replace("getfree_", "")
    if jid in ("dash_aurora", "dash_nexus"):
        nome = "Aurora" if jid == "dash_aurora" else "Nexus"
        await c.answer(f"O link do {nome} está temporariamente removido. Nenhum arquivo foi enviado.", show_alert=True)
        return
    await c.answer("A enviar ficheiro...")
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, link FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, link = row
    if not link or not link.strip():
        return await c.answer(f"O link de {n} está temporariamente indisponível. Nenhum arquivo foi enviado.", show_alert=True)
    await c.message.answer(f"📦 A preparar a entrega de: **{n}**...")
    await entregar_conteudo(c.from_user.id, link, n)

@dp.callback_query(F.data.startswith("pix_"))
async def cb_px(c):
    jid = c.data.replace("pix_", "")
    await c.answer("A gerar Pix...")
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, preco FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, pr = row
    if c.message.photo:
        await c.message.edit_caption(caption="⏳ A ligar ao Mercado Pago...", reply_markup=None)
    else:
        await c.message.edit_text("⏳ A ligar ao Mercado Pago...")
    pdata = {
        "transaction_amount": float(pr),
        "description": f"X360 - {n}",
        "payment_method_id": "pix",
        "payer": {"email": f"c{c.from_user.id}@gmail.com", "first_name": c.from_user.first_name or "Gamer"}
    }
    try:
        p = sdk.payment().create(pdata).get("response", {})
        pid, px = p["id"], p["point_of_interaction"]["transaction_data"]["qr_code"]
    except Exception as e:
        return await c.message.edit_text(f"❌ Erro Pix: {e}")
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO pedidos VALUES (?, ?, ?, 'pending')", (pid, c.from_user.id, jid))
        await db.commit()
    qr = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={urllib.parse.quote(px)}"
    kb = IKM(inline_keyboard=[[btn("🟢 Ja Paguei (Liberar Download)", cb=f"chk_{pid}")], [btn("◀️ Cancelar", cb="voltar_ini")]])
    await c.message.delete()
    await c.message.answer_photo(photo=qr, caption=f"🎮 **{n}**\n💰 R$ {pr:.2f}\n\n`{px}`", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("chk_"))
async def cb_ck(c):
    await c.answer("A verificar...")
    pid = int(c.data.split("_")[1])
    if sdk.payment().get(pid).get("response", {}).get("status") == "approved":
        async with aiosqlite.connect(DB) as db:
            res = await db.execute("SELECT jid, st FROM pedidos WHERE pid = ?", (pid,))
            ped = await res.fetchone()
            if not ped or ped[1] == "delivered":
                return await c.answer("Ja entregue!", show_alert=True)
            r2 = await db.execute("SELECT nome, link FROM jogos WHERE id = ?", (ped[0],))
            n, l = await r2.fetchone()
            await db.execute("UPDATE pedidos SET st = 'delivered' WHERE pid = ?", (pid,))
            await db.commit()
        await c.message.answer(f"🎉 **PAGAMENTO CONFIRMADO!**\n\n🎮 A entregar: **{n}**...")
        await entregar_conteudo(c.from_user.id, l, n)
    else:
        await c.answer("⏳ Aguardando compensacao Pix...", show_alert=True)

@dp.callback_query(F.data == "voltar_ini")
async def cb_vi(c):
    await c.answer()
    await safe_edit(c, TXT_INI, kb_inicio())

@dp.callback_query(F.data == "ajuda_b")
async def cb_ab(c):
    await c.answer()
    await safe_edit(c, "🔍 **Como Pesquisar:**\nEnvie `/buscar` e o nome.\n\nExemplo: `/buscar halo`", IKM(inline_keyboard=[[btn("◀️ Voltar", cb="voltar_ini")]]))

@dp.callback_query(F.data == "tut_inst")
async def cb_ti(c):
    await c.answer()
    t = "📖 **Tutorial Rapido:**\n\n1. Pendrive em FAT32.\n2. **GOD:** em `Content\\0000000000000000`\n3. **XEX:** em `Games`\n4. Abra a Aurora ou Nexus!"
    await safe_edit(c, t, IKM(inline_keyboard=[[btn("◀️ Voltar", cb="voltar_ini")]]))

@dp.callback_query(F.data == "noop")
async def cb_np(c):
    await c.answer()

async def ping(request):
    html = "<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"theme-color\" content=\"#07110d\"><title>X360 TECH BR | Loja Gamer</title><style>:root{color-scheme:dark;--g:#39ff88;--b:#39c5ff}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 15% 15%,#103b2a,transparent 40%),radial-gradient(ellipse at 90% 70%,#102d4b,transparent 42%),#07110d;color:#f4fff8;font-family:Arial,sans-serif;display:grid;place-items:center;overflow-x:hidden}body:before{content:\"\";position:fixed;inset:-40%;pointer-events:none;background:conic-gradient(from 0deg,transparent,#39ff8812,transparent,#39c5ff12,transparent);animation:spin 22s linear infinite}.wrap{position:relative;width:min(920px,92vw);padding:28px 0}.logo{font-weight:900;letter-spacing:2px;color:var(--g);text-shadow:0 0 18px #39ff8866}.panel{margin-top:22px;padding:clamp(24px,5vw,54px);border:1px solid #39ff8855;border-radius:28px;background:#07110ddd;box-shadow:0 0 35px #39ff8815;animation:appear .8s ease-out both}.tag{display:inline-block;padding:8px 12px;border:1px solid #39c5ff77;border-radius:999px;color:var(--b);font-size:12px;font-weight:bold;letter-spacing:1.5px}h1{font-size:clamp(34px,7vw,68px);line-height:1.02;margin:20px 0 14px}h1 span{color:var(--g);text-shadow:0 0 25px #39ff8844}p{color:#b8c9c0;line-height:1.7;max-width:650px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:28px 0}.tile{padding:18px;border-radius:16px;background:linear-gradient(135deg,#12251c,#0b1720);border:1px solid #ffffff16;transition:transform .2s,border-color .2s}.tile:hover{transform:translateY(-4px);border-color:#39ff8888}.tile b{display:block;margin:10px 0 5px}.tile small{color:#a6b9af;line-height:1.5}.cta{display:inline-block;text-decoration:none;font-weight:900;color:#04140b;background:linear-gradient(100deg,var(--g),#a2ffce);padding:16px 22px;border-radius:12px;box-shadow:0 0 22px #39ff8833}.note{font-size:12px;color:#7e9689;margin-top:24px}@keyframes spin{to{transform:rotate(360deg)}}@keyframes appear{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}</style></head><body><main class=\"wrap\"><div class=\"logo\">🎮 X360 TECH BR</div><section class=\"panel\"><div class=\"tag\">SUA CENTRAL XBOX 360</div><h1>Seu próximo jogo.<br><span>Sua próxima aventura.</span></h1><p>Um espaço gamer para encontrar jogos de Xbox 360, conteúdos gratuitos e dashboards. Entre pelo bot para navegar no catálogo e acessar as opções disponíveis.</p><div class=\"grid\"><div class=\"tile\"><span style=\"font-size:28px\">🎮</span><b>Catálogo de jogos</b><small>Explore categorias e encontre seu próximo jogo.</small></div><div class=\"tile\"><span style=\"font-size:28px\">🎁</span><b>Conteúdos gratuitos</b><small>Acesse a área de desbloqueios disponíveis.</small></div><div class=\"tile\"><span style=\"font-size:28px\">🧩</span><b>Dashboards</b><small>Conheça as opções Aurora e Nexus.</small></div></div><a class=\"cta\" href=\"https://t.me/Xbox360StoreBot\">🚀 ENTRAR NA LOJA PELO TELEGRAM</a><div class=\"note\">X360 TECH BR · GOD / XEX · Visual otimizado para celular</div></section></main></body></html>"
    return web.Response(text=html, content_type="text/html")

def make_web_app():
    app = web.Application()
    app.router.add_get("/", ping)
    app.router.add_get("/healthz", ping)
    return app

async def main():
    criar_banner()
    await init_db()
    app = make_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🚀 Web server ativo na porta {PORT}!")
    print("🚀 Polling do Bot iniciado!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
