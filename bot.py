import os, asyncio, urllib.parse, aiosqlite, mercadopago, re
from datetime import datetime
from zoneinfo import ZoneInfo
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

class FormEdicao(StatesGroup):
    valor = State()

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

def normalizar_categoria(valor):
    """Accept category keys, visible labels, and common names typed by the admin."""
    raw = str(valor or "").strip().lower()
    aliases = {
        "jogos modificados": "modificados",
        "jogo modificado": "modificados",
        "modificados xbox 360": "modificados",
        "jogos modificados para xbox 360": "modificados",
        "grátis": "gratis",
        "desbloqueio": "gratis",
        "desbloqueios": "gratis",
        "dashboard": "dashboards",
        "dashboards": "dashboards",
    }
    if raw in aliases:
        return aliases[raw]
    if raw in CATS or raw in ("gratis", "dashboards"):
        return raw
    # Match the visible category label even if the user omits its emoji.
    for key, label in CATS.items():
        clean_label = re.sub(r"[^a-z0-9 ]", " ", label.lower())
        clean_label = re.sub(r"\s+", " ", clean_label).strip()
        clean_raw = re.sub(r"[^a-z0-9 ]", " ", raw)
        clean_raw = re.sub(r"\s+", " ", clean_raw).strip()
        if clean_raw == clean_label or clean_raw in (key.replace("_", " "),):
            return key
    return None

def hoje_local():
    return datetime.now(ZoneInfo("America/Belem")).date().isoformat()

def preco_efetivo(preco, promo_price=None, promo_until=None):
    if promo_price is not None and promo_until and str(promo_until) >= hoje_local():
        try:
            promo, base = float(promo_price), float(preco or 0)
            if 0 <= promo < base:
                return promo
        except (TypeError, ValueError):
            pass
    return float(preco or 0)

def texto_preco(preco, promo_price=None, promo_until=None):
    base = float(preco or 0)
    atual = preco_efetivo(base, promo_price, promo_until)
    if atual < base:
        return f"🔥 PROMOÇÃO: R$ {atual:.2f} (antes R$ {base:.2f}; até {promo_until})"
    return f"💰 R$ {base:.2f}"

def kb_admin():
    return IKM(inline_keyboard=[
        [btn("🆕 Cadastrar produto", cb="adm_help_cadastro", s="primary")],
        [btn("✏️ Editar produto existente", cb="adm_help_editar", s="success")],
        [btn("💰 Alterar preço", cb="adm_help_preco", s="success")],
        [btn("🏷️ Criar promoção", cb="adm_help_promo", s="success")],
        [btn("⏹️ Encerrar promoção", cb="adm_help_fimpromo", s="primary")],
        [btn("📦 Pausar / reativar produto", cb="adm_help_ativo", s="primary")],
        [btn("◀️ Voltar ao início", cb="voltar_ini", s="primary")]
    ])

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
        # Backward-compatible migration for one-time admin sale notifications.
        cols = await db.execute("PRAGMA table_info(pedidos)")
        col_names = {row[1] for row in await cols.fetchall()}
        if "admin_notified" not in col_names:
            await db.execute("ALTER TABLE pedidos ADD COLUMN admin_notified INTEGER NOT NULL DEFAULT 0")
        game_cols = await db.execute("PRAGMA table_info(jogos)")
        game_col_names = {row[1] for row in await game_cols.fetchall()}
        if "promo_price" not in game_col_names:
            await db.execute("ALTER TABLE jogos ADD COLUMN promo_price REAL")
        if "promo_until" not in game_col_names:
            await db.execute("ALTER TABLE jogos ADD COLUMN promo_until TEXT")
        if "active" not in game_col_names:
            await db.execute("ALTER TABLE jogos ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        itens = [
            ('abadavatar', 'Desbloqueio AbadAvatar', 'gratis', 0.0, 'https://t.me/c/4434900523/2', 'Guia e ficheiros para desbloqueio AbadAvatar.'),
            ('rockband', 'Desbloqueio Rock Band', 'gratis', 0.0, 'https://t.me/c/4434900523/2', 'Ficheiros essenciais para desbloqueio Rock Band.'),
            ('dash_aurora', 'Aurora', 'dashboards', 0.0, 'https://t.me/c/4434900523/2', 'Interface moderna com capas automaticas.'),
            ('dash_nexus', 'Nexus', 'dashboards', 0.0, 'https://t.me/c/4434900523/2', 'Dashboard com menus rapidos e plugins.'),
            ('limbo', 'Limbo', 'plataforma', 4.99, 'https://t.me/c/4434900523/5', 'Jogo completo Limbo para Xbox 360 RGH/JTAG.'),
            ('crazy_taxi', 'Crazy Taxi', 'corrida', 4.99, 'https://t.me/c/4434900523/8', 'Classico Crazy Taxi pronto para pendrive.')
        ]
        # Seeds are added only when missing; never overwrite or delete catalog entries on startup.
        await db.executemany("INSERT OR IGNORE INTO jogos (id, nome, cat, preco, link, desc) VALUES (?,?,?,?,?,?)", itens)
        # Several items were accidentally seeded with the Nexus post URL.
        # Keep that URL for Nexus only; disable it for Aurora and unrelated unlocks
        # until their correct Telegram post links are supplied.
        await db.execute(
            "UPDATE jogos SET link = '' WHERE id IN ('dash_aurora', 'abadavatar', 'rockband') "
            "AND link = 'https://t.me/c/4434900523/2'"
        )
        await db.commit()

SALE_NOTIFY_LOCK = asyncio.Lock()

async def notify_admin_sale(pid, payment=None):
    """Notify the shop owner once, only after Mercado Pago confirms approval."""
    if not sdk:
        return False
    if payment is None:
        try:
            payment = sdk.payment().get(int(pid)).get("response", {})
        except Exception as e:
            print("Erro ao verificar pagamento para notificacao:", e)
            return False
    if str(payment.get("status", "")).lower() != "approved":
        return False

    # Serialize notifications in this process. Save the sent flag only after
    # Telegram accepts the message, so a send failure does not suppress retries.
    async with SALE_NOTIFY_LOCK:
        async with aiosqlite.connect(DB) as db:
            cur = await db.execute(
                "SELECT p.uid, p.jid, p.st, p.admin_notified, j.nome, j.preco "
                "FROM pedidos p LEFT JOIN jogos j ON j.id = p.jid WHERE p.pid = ?",
                (int(pid),)
            )
            order = await cur.fetchone()
        if not order:
            return False
        if int(order[3] or 0) == 1:
            return True

        uid, jid, order_status, _already_notified, game_name, price = order
        amount = price if price is not None else payment.get("transaction_amount", 0)
        message = (
            "🛒 VENDA CONFIRMADA — X360 TECH BR\\n\\n"
            f"🎮 Jogo: {game_name or jid}\\n"
            f"💰 Valor: R$ {float(amount or 0):.2f}\\n"
            "💳 Pagamento: Pix aprovado pelo Mercado Pago\\n"
            f"🧾 Pedido: {int(pid)}\\n"
            f"👤 Telegram do cliente: {int(uid)}\\n"
            f"📦 Entrega: {'concluída' if order_status == 'delivered' else 'aguardando/conferindo'}"
        )
        try:
            await bot.send_message(ADMIN_ID, message)
        except Exception as e:
            print("Falha ao enviar notificacao de venda:", e)
            return False

        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE pedidos SET admin_notified = 1 WHERE pid = ?", (int(pid),))
            await db.commit()
        print("Notificacao de venda enviada ao administrador para pedido", pid)
        return True

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
        c1 = await db.execute("SELECT COUNT(*) FROM jogos WHERE cat = ? AND active = 1", (ck,))
        tot = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT id, nome, preco, promo_price, promo_until FROM jogos WHERE cat = ? AND active = 1 ORDER BY nome ASC LIMIT 6 OFFSET ?", (ck, off))
        rows = await c2.fetchall()
    b = []
    for r in rows:
        jid_item = str(r[0])
        nome_item = str(r[1])
        preco_item = preco_efetivo(r[2], r[3], r[4])
        label_btn = ("🔥 " if preco_item < float(r[2] or 0) else "🔵 ") + nome_item + " - R$ " + f"{preco_item:.2f}"
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

@dp.message(Command("admin"))
async def cmd_admin(m):
    if m.from_user.id != ADMIN_ID:
        return
    await m.answer(
        "⚙️ Painel administrativo — X360 TECH BR\n\n"
        "Cadastrar produto: /cadastrar Nome | categoria | preço | link | descrição\n"
        "Editar produto existente: /editar ID | campo | novo valor\n"
        "Campos editáveis: nome, categoria, preco, link, descricao\n"
        "Alterar preço: /preco ID_DO_JOGO | novo_preço\n"
        "Criar promoção: /promocao ID_DO_JOGO | preço_promocional | AAAA-MM-DD\n"
        "Encerrar promoção: /fim_promocao ID_DO_JOGO\n"
        "Pausar/reativar: /pausar ID_DO_JOGO ou /ativar ID_DO_JOGO\n\n"
        "Use /produtos para consultar os IDs.",
        reply_markup=kb_admin()
    )

async def mostrar_produtos_admin(m):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT id, nome, preco, promo_price, promo_until, active FROM jogos ORDER BY nome")
        rows = await cur.fetchall()
    if not rows:
        return await m.answer("Nenhum produto cadastrado.")
    lines = ["📦 Produtos cadastrados — toque em um produto para editar:"]
    buttons = []
    for jid, nome, preco, promo, until, active in rows[:80]:
        status = "ATIVO" if active else "PAUSADO"
        lines.append(f"• {nome} | ID: {jid} | {texto_preco(preco, promo, until)} | {status}")
        buttons.append([btn(("✏️ " + str(nome))[:55], cb="editprod_" + str(jid), s="primary")])
    if len(rows) > 80:
        lines.append(f"Mostrando os primeiros 80 de {len(rows)} produtos.")
    buttons.append([btn("❌ Fechar", cb="cancelar_fsm")])
    await m.answer("\n".join(lines), reply_markup=IKM(inline_keyboard=buttons))

@dp.message(Command("produtos"))
async def cmd_produtos(m):
    if m.from_user.id != ADMIN_ID:
        return
    await mostrar_produtos_admin(m)

@dp.message(Command("editar"))
async def cmd_editar(m):
    if m.from_user.id != ADMIN_ID:
        return
    payload = m.text.partition(" ")[2].strip() if m.text else ""
    if not payload:
        return await mostrar_produtos_admin(m)
    parts = [x.strip() for x in payload.split("|", 2)]
    if len(parts) != 3 or not all(parts):
        return await m.answer("Para editar sem digitar IDs, use /editar e toque no produto da lista.\nFormato alternativo: /editar ID | campo | novo valor")
    jid, field, value = parts
    await salvar_edicao(m, jid.lower(), field.lower(), value)

async def salvar_edicao(m, jid, field, value):
    allowed = {"nome", "categoria", "preco", "link", "descricao"}
    if field not in allowed:
        return await m.answer("Campo inválido. Use: nome, categoria, preco, link ou descricao.")
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT nome FROM jogos WHERE id = ?", (jid,))
        row = await cur.fetchone()
        if not row:
            return await m.answer("Não encontrei esse ID. Use /editar e selecione o produto na lista.")
        if field == "nome":
            if not value:
                return await m.answer("O nome não pode ficar vazio.")
            column, new_value = "nome", value
        elif field == "categoria":
            cat = normalizar_categoria(value)
            if not cat:
                return await m.answer("Categoria inválida. Envie uma categoria válida, como modificados ou servidores_furtivos.")
            column, new_value = "cat", cat
        elif field == "preco":
            try:
                new_value = float(value.replace(",", "."))
                if new_value < 0 or new_value == float("inf") or new_value != new_value:
                    raise ValueError()
            except ValueError:
                return await m.answer("Preço inválido. Envie, por exemplo, 9,99.")
            column = "preco"
        elif field == "link":
            if not (value.startswith("https://") or value.startswith("http://") or value.startswith("tg://")):
                return await m.answer("Link inválido. Use um endereço https://, http:// ou tg://.")
            column, new_value = "link", value
        else:
            column, new_value = "desc", value
        await db.execute(f"UPDATE jogos SET {column} = ? WHERE id = ?", (new_value, jid))
        if field == "preco":
            await db.execute("UPDATE jogos SET promo_price = NULL, promo_until = NULL WHERE id = ?", (jid,))
        await db.commit()
    await m.answer(f"✅ Produto atualizado!\nProduto: {row[0]}\nCampo: {field}\nNovo valor: {new_value}\nID mantido: {jid}")

@dp.callback_query(F.data.startswith("editprod_"))
async def cb_editar_escolhe_produto(c, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("Sem autorização.", show_alert=True)
    jid = c.data.removeprefix("editprod_")
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT nome FROM jogos WHERE id = ?", (jid,))
        row = await cur.fetchone()
    if not row:
        return await c.answer("Produto não encontrado.", show_alert=True)
    fields = [
        [btn("✏️ Alterar nome", cb=f"editfield|{jid}|nome")],
        [btn("📂 Alterar categoria", cb=f"editfield|{jid}|categoria")],
        [btn("💰 Alterar preço", cb=f"editfield|{jid}|preco")],
        [btn("🔗 Alterar link", cb=f"editfield|{jid}|link")],
        [btn("📝 Alterar descrição", cb=f"editfield|{jid}|descricao")],
        [btn("◀️ Voltar aos produtos", cb="adm_voltar_produtos")]
    ]
    await c.answer()
    await safe_edit(c, "Produto selecionado: " + str(row[0]) + "\n\nO que deseja alterar?", IKM(inline_keyboard=fields))

@dp.callback_query(F.data.startswith("editfield|"))
async def cb_editar_escolhe_campo(c, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("Sem autorização.", show_alert=True)
    _, jid, field = c.data.split("|", 2)
    await state.update_data(edit_jid=jid, edit_field=field)
    await state.set_state(FormEdicao.valor)
    labels = {"nome":"novo nome", "categoria":"nova categoria", "preco":"novo preço (ex.: 6,99)", "link":"novo link", "descricao":"nova descrição"}
    await c.answer()
    await safe_edit(c, f"Envie agora o {labels.get(field, field)}.\n\nEnvie /cancelar para desistir.", IKM(inline_keyboard=[[btn("❌ Cancelar", cb="cancelar_fsm")]]))

@dp.message(FormEdicao.valor)
async def processa_valor_edicao(m, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
    if m.text and m.text.strip().lower() == "/cancelar":
        await state.clear()
        return await m.answer("Edição cancelada.")
    data = await state.get_data()
    jid, field = data.get("edit_jid"), data.get("edit_field")
    if not jid or not field or not m.text:
        return await m.answer("Envie um valor em texto ou use /cancelar.")
    # Keep the state if validation fails, so the admin can retry without restarting.
    allowed = {"nome", "categoria", "preco", "link", "descricao"}
    if field not in allowed:
        await state.clear()
        return await m.answer("Campo inválido. Recomece com /editar.")
    value = m.text.strip()
    if field == "categoria":
        new_value = normalizar_categoria(value)
        if not new_value:
            return await m.answer("Categoria inválida. Tente: modificados, servidores_furtivos, corrida, aventura.")
    elif field == "preco":
        try:
            new_value = float(value.replace(",", "."))
            if new_value < 0 or new_value == float("inf") or new_value != new_value:
                raise ValueError()
        except ValueError:
            return await m.answer("Preço inválido. Envie, por exemplo, 6,99.")
    elif field == "link":
        if not (value.startswith("https://") or value.startswith("http://") or value.startswith("tg://")):
            return await m.answer("Link inválido. O link deve começar com https://, http:// ou tg://.")
        new_value = value
    else:
        new_value = value
    column = {"nome":"nome", "categoria":"cat", "preco":"preco", "link":"link", "descricao":"desc"}[field]
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT nome FROM jogos WHERE id = ?", (jid,))
        row = await cur.fetchone()
        if not row:
            await state.clear()
            return await m.answer("Não encontrei o produto no banco de dados. Use /editar para selecionar novamente.")
        await db.execute(f"UPDATE jogos SET {column} = ? WHERE id = ?", (new_value, jid))
        if field == "preco":
            await db.execute("UPDATE jogos SET promo_price = NULL, promo_until = NULL WHERE id = ?", (jid,))
        await db.commit()
    await state.clear()
    await m.answer(f"✅ Produto atualizado!\nAntes: {row[0]}\nCampo: {field}\nNovo valor: {new_value}\nID mantido: {jid}")

@dp.callback_query(F.data == "adm_voltar_produtos")
async def cb_adm_voltar_produtos(c):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("Sem autorização.", show_alert=True)
    await c.answer()
    await mostrar_produtos_admin(c.message)

@dp.message(Command("preco"))
async def cmd_preco(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = [x.strip() for x in m.text.partition(" ")[2].split("|", 1)]
    if len(parts) != 2 or not parts[0]:
        return await m.answer("Formato: /preco ID_DO_JOGO | 5,99")
    jid, raw = parts
    try:
        price = float(raw.replace(",", "."))
        if price < 0 or price == float("inf"):
            raise ValueError()
    except ValueError:
        return await m.answer("Preço inválido. Exemplo: /preco limbo | 5,99")
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT nome FROM jogos WHERE id = ?", (jid.lower(),))
        row = await cur.fetchone()
        if not row:
            return await m.answer("Não encontrei esse ID. Consulte /produtos.")
        await db.execute("UPDATE jogos SET preco = ?, promo_price = NULL, promo_until = NULL WHERE id = ?", (price, jid.lower()))
        await db.commit()
    await m.answer(f"Preço de {row[0]} atualizado para R$ {price:.2f}. Promoção anterior encerrada, se existia.")

@dp.message(Command("promocao"))
async def cmd_promocao(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = [x.strip() for x in m.text.partition(" ")[2].split("|", 2)]
    if len(parts) != 3:
        return await m.answer("Formato: /promocao ID_DO_JOGO | preço_promocional | AAAA-MM-DD\nExemplo: /promocao limbo | 2,99 | 2026-11-30")
    jid, raw_price, until = parts
    try:
        promo = float(raw_price.replace(",", "."))
        valid_until = datetime.strptime(until, "%Y-%m-%d").date().isoformat()
        if valid_until < hoje_local() or promo < 0 or promo == float("inf"):
            raise ValueError()
    except ValueError:
        return await m.answer("Confira o preço e a data. Use AAAA-MM-DD e uma data de hoje em diante.")
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT nome, preco FROM jogos WHERE id = ?", (jid.lower(),))
        row = await cur.fetchone()
        if not row:
            return await m.answer("Não encontrei esse ID. Consulte /produtos.")
        if promo >= float(row[1] or 0):
            return await m.answer(f"O preço promocional precisa ser menor que o preço normal (R$ {float(row[1] or 0):.2f}).")
        await db.execute("UPDATE jogos SET promo_price = ?, promo_until = ? WHERE id = ?", (promo, valid_until, jid.lower()))
        await db.commit()
    await m.answer(f"Promoção programada!\n\nJogo: {row[0]}\nDe R$ {float(row[1]):.2f} por R$ {promo:.2f}\nAté: {valid_until}")

@dp.message(Command("fim_promocao"))
async def cmd_fim_promocao(m):
    if m.from_user.id != ADMIN_ID:
        return
    jid = m.text.partition(" ")[2].strip().lower()
    if not jid:
        return await m.answer("Formato: /fim_promocao ID_DO_JOGO")
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT nome FROM jogos WHERE id = ?", (jid,))
        row = await cur.fetchone()
        if not row:
            return await m.answer("Não encontrei esse ID. Consulte /produtos.")
        await db.execute("UPDATE jogos SET promo_price = NULL, promo_until = NULL WHERE id = ?", (jid,))
        await db.commit()
    await m.answer(f"Promoção encerrada para {row[0]}.")

@dp.message(Command("pausar"))
@dp.message(Command("ativar"))
async def cmd_status_produto(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Informe o ID. Consulte /produtos.")
    active = 0 if parts[0].lower().endswith("pausar") else 1
    jid = parts[1].strip().lower()
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT nome FROM jogos WHERE id = ?", (jid,))
        row = await cur.fetchone()
        if not row:
            return await m.answer("Não encontrei esse ID. Consulte /produtos.")
        await db.execute("UPDATE jogos SET active = ? WHERE id = ?", (active, jid))
        await db.commit()
    await m.answer(("Produto pausado: " if not active else "Produto reativado: ") + str(row[0]))

@dp.callback_query(F.data.startswith("adm_help_"))
async def cb_admin_help(c):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("Sem autorização.", show_alert=True)
    key = c.data.replace("adm_help_", "")
    messages = {
        "cadastro": "Para cadastrar um produto novo: /cadastrar Nome | categoria | preço | link | descrição",
        "editar": "Para editar um produto existente: /editar ID | campo | novo valor\nCampos: nome, categoria, preco, link, descricao\nExemplo: /editar servidor_furtivo | preco | 9,99\nO ID não muda. Consulte /produtos.",
        "preco": "Para alterar preço: /preco ID_DO_JOGO | 5,99\nConsulte /produtos para ver os IDs.",
        "promo": "Para criar promoção: /promocao ID_DO_JOGO | 2,99 | 2026-11-30",
        "fimpromo": "Para encerrar antes da data: /fim_promocao ID_DO_JOGO",
        "ativo": "Para pausar: /pausar ID_DO_JOGO\nPara reativar: /ativar ID_DO_JOGO"
    }
    await c.answer()
    await c.message.answer(messages.get(key, "Use /admin para ver as opções."))

@dp.message(Command("stats"))
@dp.message(Command("total"))
async def cmd_estatisticas(m):
    if m.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT cat FROM jogos WHERE preco > 0 AND active = 1")
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
    # Cadastro rapido em uma unica mensagem:
    # /cadastrar Nome | categoria | preco | link | descricao
    payload = m.text.partition(" ")[2].strip() if m.text else ""
    if payload:
        partes = [p.strip() for p in payload.split("|", 4)]
        if len(partes) < 4:
            return await m.answer(
                "⚡ **Cadastro rapido**\n\n"
                "Envie tudo em uma mensagem neste formato:\n"
                "`/cadastrar Nome do jogo | modificados | 4,99 | https://t.me/c/4434900523/11 | Descricao curta`\n\n"
                "Categorias: " + ", ".join(CATS.keys()) + ", gratis, dashboards\n"
                "Para cadastrar por etapas, envie apenas /cadastrar.",
                parse_mode="Markdown"
            )
        nome, cat_raw, preco_raw, link = partes[:4]
        desc = partes[4] if len(partes) > 4 and partes[4] else nome
        cat = normalizar_categoria(cat_raw)
        if not cat:
            return await m.answer("⚠️ Categoria inválida. Use uma destas chaves: " + ", ".join(CATS.keys()) + ", gratis, dashboards.")
        try:
            preco = float(preco_raw.replace(",", "."))
            if preco < 0:
                raise ValueError()
        except ValueError:
            return await m.answer("⚠️ Preço inválido. Exemplo: 4,99")
        if not nome or not (link.startswith("https://") or link.startswith("http://") or link.startswith("tg://")):
            return await m.answer("⚠️ Confira o nome e o link. O link deve começar com https://, http:// ou tg://.")
        jid = slugify(nome)
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO jogos (id, nome, cat, preco, link, desc) VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
                (jid, nome, cat, preco, link, desc)
            )
            await db.commit()
        await m.answer(
            "✅ **Cadastro concluído!**\n\n"
            "🎮 " + nome + "\n"
            "📂 " + str(CATS.get(cat, cat)) + "\n"
            "💰 R$ " + f"{preco:.2f}" + "\n"
            "🔗 Link salvo.",
            parse_mode="Markdown"
        )
        return
    await state.clear()
    await state.set_state(FormCadastro.nome)
    cancel_kb = IKM(inline_keyboard=[[btn("❌ Cancelar", cb="cancelar_fsm")]])
    await m.answer(
        "📝 **Cadastro por etapas:** Qual o nome do jogo?\n\n"
        "💡 Para cadastrar tudo de uma vez, use:\n"
        "`/cadastrar Nome | modificados | 4,99 | link do Telegram | descricao`",
        reply_markup=cancel_kb, parse_mode="Markdown"
    )

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
            "INSERT INTO jogos (id, nome, cat, preco, link, desc) VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
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
    cat = normalizar_categoria(cat_raw) or "acao"
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
            "INSERT INTO jogos (id, nome, cat, preco, link, desc) VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
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
            "INSERT INTO jogos (id, nome, cat, preco, link, desc) VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cat=excluded.cat, preco=excluded.preco, link=excluded.link, desc=excluded.desc",
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
        c = await db.execute("SELECT id, nome, preco, promo_price, promo_until FROM jogos WHERE nome LIKE ? AND active = 1 LIMIT 8", ("%" + t + "%",))
        rows = await c.fetchall()
    if not rows:
        return await m.answer("Nenhum jogo encontrado.")
    b = []
    for r in rows:
        jid_item = str(r[0])
        nome_item = str(r[1])
        preco_item = preco_efetivo(r[2], r[3], r[4])
        label_btn = ("🔥 " if preco_item < float(r[2] or 0) else "🔵 ") + nome_item + " - R$ " + f"{preco_item:.2f}"
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
        res = await db.execute("SELECT nome, preco, desc, cat, link, promo_price, promo_until, active FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, p, d, ck, link, promo_price, promo_until, active = row
    if not active:
        return await c.message.answer("Este produto está temporariamente indisponível.")
    preco_atual = preco_efetivo(p, promo_price, promo_until)
    v = "menu_desb" if ck == "gratis" else ("menu_dash" if ck == "dashboards" else "c_" + str(ck) + "_1")
    if p == 0.0:
        tx = "🎁 **" + str(n) + "** (Gratis)\n\n📝 " + str(d)
        b = [[btn("🟢 Receber Ficheiro Agora", cb="getfree_" + str(jid), s="success")], [btn("◀️ Voltar", cb=v)]]
    else:
        tx = "🎮 **" + str(n) + "**\n" + texto_preco(p, promo_price, promo_until) + " (GOD / XEX)\n\n📝 " + str(d)
        b = [[btn("🟢 Pagar R$ " + f"{preco_atual:.2f}" + " via Pix", cb="pix_" + str(jid), s="success")], [btn("◀️ Voltar", cb=v)]]
    await safe_edit(c, tx, IKM(inline_keyboard=b))

@dp.callback_query(F.data.startswith("getfree_"))
async def cb_getfree(c):
    jid = c.data.replace("getfree_", "")
    await c.answer("A enviar ficheiro...")
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, link, active FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, link, active = row
    if not active:
        return await c.message.answer("Este produto está temporariamente indisponível.")
    if not link:
        return await c.message.answer(
            "⚠️ O link deste conteúdo ainda está sendo corrigido. Nenhum arquivo foi enviado. Tente novamente mais tarde."
        )
    await c.message.answer("📦 A preparar a entrega de: **" + str(n) + "**...")
    try:
        entregue = await entregar_conteudo(c.from_user.id, link, n)
    except Exception as e:
        print("Falha na entrega gratuita:", e)
        entregue = False
    if entregue:
        nav = IKM(inline_keyboard=[
            [btn("🔵 Catálogo de Jogos", cb="menu_cat", s="primary")],
            [btn("🟢 Voltar ao Início", cb="voltar_ini", s="success")]
        ])
        await c.message.answer(
            "✅ Conteúdo enviado! O que deseja fazer agora?",
            reply_markup=nav
        )
    else:
        await c.message.answer("⚠️ Não consegui concluir o envio. Tente novamente mais tarde.")

@dp.callback_query(F.data.startswith("pix_"))
async def cb_px(c):
    jid = c.data.replace("pix_", "", 1)
    await c.answer("A gerar Pix...")
    if not sdk:
        return await c.message.answer("❌ Pagamento indisponivel no momento. Tente novamente mais tarde.")
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, preco, promo_price, promo_until, active FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, base_price, promo_price, promo_until, active = row
    if not active:
        return await c.message.answer("Este produto está temporariamente indisponível.")
    pr = preco_efetivo(base_price, promo_price, promo_until)
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
        await db.execute("INSERT INTO pedidos (pid, uid, jid, st) VALUES (?, ?, ?, 'pending')", (pid, c.from_user.id, jid))
        await db.commit()
    qr = "https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=" + urllib.parse.quote(px)
    kb = IKM(inline_keyboard=[[btn("🟢 Ja Paguei (Liberar Download)", cb="chk_" + str(pid), s="success")], [btn("◀️ Cancelar", cb="voltar_ini")]])
    await c.message.delete()
    caption_txt = "🎮 **" + str(n) + "**\n" + texto_preco(base_price, promo_price, promo_until) + "\n\n`" + str(px) + "`"
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
    await notify_admin_sale(pid, resp)
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
        nav = IKM(inline_keyboard=[
            [btn("🔵 Catálogo de Jogos", cb="menu_cat", s="primary")],
            [btn("🟢 Voltar ao Início", cb="voltar_ini", s="success")]
        ])
        await c.message.answer(
            "✅ Entrega concluída. Guarde esta conversa para consultar o produto.\n\nO que deseja fazer agora?",
            reply_markup=nav
        )
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

async def mercadopago_webhook(request):
    """Receive Mercado Pago events; always verify payment status via the API."""
    if not sdk:
        return web.Response(text="Mercado Pago not configured", status=503)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payment_id = request.query.get("data.id") or request.query.get("id")
    if not payment_id and isinstance(payload, dict):
        data = payload.get("data") or {}
        if isinstance(data, dict):
            payment_id = data.get("id")
        payment_id = payment_id or payload.get("id")
    topic = request.query.get("type") or request.query.get("topic")
    if not payment_id:
        return web.Response(text="Event received; no payment id", status=200)
    try:
        payment = sdk.payment().get(int(payment_id)).get("response", {})
        payment_status = str(payment.get("status", "")).lower()
        if payment_status == "approved":
            # Mercado Pago can notify very quickly; if the order row has not
            # been saved yet, return 5xx so the provider can retry the event.
            async with aiosqlite.connect(DB) as db:
                cur = await db.execute("SELECT 1 FROM pedidos WHERE pid = ?", (int(payment_id),))
                order_exists = await cur.fetchone()
            if not order_exists:
                print("Webhook chegou antes do pedido ser gravado; solicitando nova tentativa:", payment_id)
                return web.Response(text="Order not ready; retry later", status=503)
            notified = await notify_admin_sale(int(payment_id), payment)
            if not notified:
                print("Notificacao pendente; solicitando nova tentativa do webhook:", payment_id)
                return web.Response(text="Notification not completed; retry later", status=503)
        print("Webhook Mercado Pago recebido:", topic or payload.get("type", "unknown"), "payment", payment_id, "status", payment_status or "unknown")
        return web.Response(text="OK", status=200)
    except Exception as e:
        print("Erro ao processar webhook Mercado Pago:", repr(e))
        return web.Response(text="Temporary processing error", status=500)

def make_web_app():
    app = web.Application()
    app.router.add_get("/", ping)
    app.router.add_get("/healthz", ping)
    app.router.add_post("/mercadopago/webhook", mercadopago_webhook)
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

