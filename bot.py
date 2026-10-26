import os, asyncio, urllib.parse, aiosqlite, mercadopago, re, time, json, base64
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup as IKM, WebAppInfo

TOKEN = os.getenv("BOT_TOKEN", "").strip()
MP_KEY = os.getenv("MP_ACCESS_TOKEN", "").strip()
PORT = int(os.getenv("PORT", 10000))
ADMIN_ID = 1858295769

sdk = mercadopago.SDK(MP_KEY) if MP_KEY else None
bot = Bot(token=TOKEN)
dp = Dispatcher()
DB = "x360_store.db"
BANNER_PATH = "x360_banner.png"
START_TIME = time.monotonic()

# O catálogo permanente fica em um repositório privado separado do código do bot.
GITHUB_CATALOG_TOKEN = os.getenv("GITHUB_CATALOG_TOKEN", "").strip()
GITHUB_CATALOG_REPO = os.getenv(
    "GITHUB_CATALOG_REPO", "luizrodriguesueap-create/x360techbr-catalog"
).strip()
GITHUB_CATALOG_URL = f"https://api.github.com/repos/{GITHUB_CATALOG_REPO}/contents/catalog.json"
CATALOG_LOCK = asyncio.Lock()


async def github_catalog_request(method, payload=None):
    """Chamada autenticada à API do GitHub; nunca registra tokens nos logs."""
    if not GITHUB_CATALOG_TOKEN:
        raise RuntimeError("GITHUB_CATALOG_TOKEN não configurado")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_CATALOG_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "X360-TECH-BR-Catalog",
    }
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            method, GITHUB_CATALOG_URL, headers=headers, json=payload
        ) as response:
            try:
                data = await response.json(content_type=None)
            except Exception:
                data = {}
            return response.status, data


async def read_github_catalog():
    """Lê o catálogo durável. Retorna (SHA do arquivo, dados do catálogo)."""
    status, data = await github_catalog_request("GET")
    if status == 404:
        return None, {"version": 1, "items": []}
    if status != 200:
        raise RuntimeError(f"GitHub GET falhou com HTTP {status}")
    try:
        raw = base64.b64decode(
            "".join((data.get("content") or "").split())
        ).decode("utf-8")
        catalog = json.loads(raw)
    except Exception as exc:
        raise RuntimeError("catalog.json está inválido ou ilegível") from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("items"), list):
        raise RuntimeError("Formato inválido em catalog.json")
    return data.get("sha"), catalog


async def sync_catalog_to_github():
    """Salva o catálogo atual no repositório privado, sem implantar o bot novamente."""
    if not GITHUB_CATALOG_TOKEN:
        return False
    async with CATALOG_LOCK:
        async with aiosqlite.connect(DB) as db:
            cur = await db.execute(
                "SELECT id, nome, cat, preco, link, desc FROM jogos ORDER BY id"
            )
            rows = await cur.fetchall()
        items = [
            {
                "id": str(row[0]),
                "nome": str(row[1] or ""),
                "cat": str(row[2] or ""),
                "preco": float(row[3] or 0),
                "link": str(row[4] or ""),
                "desc": str(row[5] or ""),
            }
            for row in rows
        ]
        catalog_json = json.dumps(
            {"version": 1, "items": items},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        sha, _ = await read_github_catalog()
        payload = {
            "message": "Atualizar catálogo da X360 TECH BR",
            "content": base64.b64encode(catalog_json.encode("utf-8")).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha
        status, result = await github_catalog_request("PUT", payload)
        if status not in (200, 201):
            # Uma alteração concorrente pode trocar o SHA; não fingimos que salvou.
            raise RuntimeError(f"GitHub PUT falhou com HTTP {status}")
        return True


async def persistir_catalogo():
    """Sincroniza e informa falhas sem expor detalhes sensíveis."""
    if not GITHUB_CATALOG_TOKEN:
        return False
    try:
        return await sync_catalog_to_github()
    except Exception as exc:
        print(f"Falha ao sincronizar catálogo com GitHub: {type(exc).__name__}")
        return False

TXT_INI = (
    "🎮 **X360 TECH BR — Loja Xbox 360**\n\n"
    "Jogos digitais para Xbox 360, emuladores de consoles clássicos, conteúdos gratuitos e dashboards.\n\n"
    "_Selecione uma opção abaixo._"
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
    "adaptados": "🧪 Jogos adaptados"
}

EMULADORES = {
    "snes": "🕹️ Super Nintendo (SNES)",
    "n64": "🎮 Nintendo 64",
    "arcade": "👾 Fliperama (Arcade)",
    "megadrive": "🎮 Mega Drive",
    "ps1": "💿 PlayStation 1",
}

class FormCadastro(StatesGroup):
    nome = State()
    categoria = State()
    preco = State()
    link = State()
    descricao = State()

class BuscaJogo(StatesGroup):
    termo = State()

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
    if not link or not str(link).strip():
        return False
    chat_id, msg_id = parse_tg_link(link)
    if chat_id and msg_id:
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=chat_id, message_id=msg_id)
            return True
        except Exception as e:
            print(f"Erro ao copiar o conteúdo de {nome_jogo}: {e}")
            # Se a cópia falhar, enviar o link como alternativa também conta como entrega.
            try:
                await bot.send_message(user_id, f"📥 Download de {nome_jogo}:\n{link}")
                return True
            except Exception as fallback_error:
                print(f"Falha ao enviar link alternativo de {nome_jogo}: {fallback_error}")
                return False
    try:
        await bot.send_message(user_id, f"📥 Download de {nome_jogo}:\n{link}")
        return True
    except Exception as e:
        print(f"Falha ao enviar link de {nome_jogo}: {e}")
        return False

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS jogos (id TEXT PRIMARY KEY, nome TEXT, cat TEXT, preco REAL, link TEXT, desc TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS pedidos (pid INT PRIMARY KEY, uid INT, jid TEXT, st TEXT)")
        await db.commit()

    if GITHUB_CATALOG_TOKEN:
        # Quando o armazenamento permanente está habilitado, o GitHub é a fonte oficial.
        # Se a leitura falhar, o bot não deve continuar silenciosamente com um catálogo vazio.
        try:
            sha, catalog = await read_github_catalog()
            if sha is None:
                if not await sync_catalog_to_github():
                    raise RuntimeError("Não foi possível inicializar catalog.json")
                sha, catalog = await read_github_catalog()
            valid_items = []
            for item in catalog.get("items", []):
                if not isinstance(item, dict):
                    continue
                jid = str(item.get("id") or "").strip()
                nome = str(item.get("nome") or "").strip()
                if not jid or not nome:
                    continue
                try:
                    preco = float(item.get("preco") or 0)
                except (TypeError, ValueError):
                    preco = 0.0
                valid_items.append((
                    jid, nome, str(item.get("cat") or "acao"),
                    preco, str(item.get("link") or ""),
                    str(item.get("desc") or "")
                ))
            async with aiosqlite.connect(DB) as db:
                await db.execute("DELETE FROM jogos")
                if valid_items:
                    await db.executemany(
                        "INSERT INTO jogos VALUES (?,?,?,?,?,?)", valid_items
                    )
                await db.commit()
            print(f"Catálogo carregado do GitHub: {len(valid_items)} itens.")
        except Exception as exc:
            print(f"Falha ao carregar catálogo permanente: {type(exc).__name__}")
            raise RuntimeError(
                "Catálogo GitHub indisponível; inicialização interrompida para evitar perda de dados."
            ) from exc
    else:
        # Compatibilidade temporária até configurar o token de escrita no Render.
        async with aiosqlite.connect(DB) as db:
            itens = [
                ('abadavatar', 'Desbloqueio AbadAvatar', 'gratis', 0.0, '', 'Guia e ficheiros para desbloqueio AbadAvatar.'),
                ('rockband', 'Desbloqueio Rock Band', 'gratis', 0.0, '', 'Ficheiros essenciais para desbloqueio Rock Band.'),
                ('dash_aurora', 'Aurora', 'dashboards', 0.0, '', 'Interface moderna com capas automaticas.'),
                ('dash_nexus', 'Nexus', 'dashboards', 0.0, '', 'Dashboard com menus rapidos e plugins.')
            ]
            await db.executemany("INSERT OR IGNORE INTO jogos VALUES (?,?,?,?,?,?)", itens)
            await db.commit()
        print("ATENÇÃO: catálogo ainda usa SQLite temporário; configure GITHUB_CATALOG_TOKEN.")

def kb_inicio():
    # Poucas opções, agrupadas por função; tutorial permanece disponível.
    return IKM(inline_keyboard=[
        [btn("🎮 Jogos", cb="menu_cat", s="primary"),
         btn("🎁 Gratuitos", cb="menu_desb", s="success")],
        [btn("🧩 Dashboards", cb="menu_dash", s="success"),
         btn("🔎 Buscar", cb="ajuda_b")],
        [btn("🕹️ Emuladores", cb="menu_emu", s="primary"),
         btn("📘 Tutorial de instalação", cb="tut_inst")],
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
        g.append([btn(CATS[k[i]], cb=f"c_{k[i]}_1", s="success"), btn(CATS[k[i+1]], cb=f"c_{k[i+1]}_1", s="success")])
    if len(k) % 2:
        g.append([btn(CATS[k[-1]], cb=f"c_{k[-1]}_1", s="success")])
    g.append([btn("🟢 Ver Desbloqueios", cb="menu_desb")])
    g.append([btn("◀️ Voltar ao Inicio", cb="voltar_ini")])
    return IKM(inline_keyboard=g)

def kb_escolher_categoria():
    k = list(CATS.keys()) + list(EMULADORES.keys())
    botoes = []
    for i in range(0, len(k)-1, 2):
        botoes.append([
            btn(CATS.get(k[i], EMULADORES.get(k[i], k[i])), cb=f"selcat_{k[i]}"),
            btn(CATS.get(k[i+1], EMULADORES.get(k[i+1], k[i+1])), cb=f"selcat_{k[i+1]}")
        ])
    if len(k) % 2:
        botoes.append([btn(CATS.get(k[-1], EMULADORES.get(k[-1], k[-1])), cb=f"selcat_{k[-1]}")])
    botoes.append([btn("❌ Cancelar", cb="cancelar_fsm")])
    return IKM(inline_keyboard=botoes)

async def kb_lista(ck, pg=1, prefix="c"):
    off = (pg - 1) * 6
    async with aiosqlite.connect(DB) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM jogos WHERE cat = ?", (ck,))
        tot = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT id, nome, preco FROM jogos WHERE cat = ? ORDER BY nome ASC LIMIT 6 OFFSET ?", (ck, off))
        rows = await c2.fetchall()
    b = [[btn(f"🟢 {n} - R$ {p:.2f}", cb=f"info_{i}", s="success")] for i, n, p in rows]
    tot_p = max(1, (tot + 5) // 6)
    nav = []
    if pg > 1:
        nav.append(btn("⬅️ Anterior", cb=f"{prefix}_{ck}_{pg-1}"))
    if tot_p > 1:
        nav.append(btn(f"📄 {pg}/{tot_p}", cb="noop"))
    if pg < tot_p:
        nav.append(btn("Proxima ➡️", cb=f"{prefix}_{ck}_{pg+1}"))
    if nav:
        b.append(nav)
    b.append([btn("◀️ Voltar ao menu", cb="menu_emu" if prefix == "e" else "menu_cat")])
    return IKM(inline_keyboard=b), tot

async def safe_edit(cb, text, markup):
    # A capa aparece somente no início. Ao entrar nos menus, ela sai para liberar espaço.
    if cb.message.photo:
        try:
            await cb.message.delete()
        except Exception as e:
            print(f"Não foi possível remover a capa inicial: {e}")
        try:
            await cb.message.answer(text, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            print(f"Não foi possível enviar o menu: {e}")
        return
    # Nas telas seguintes, atualiza a mensagem existente em vez de acumular menus.
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
        return
    except Exception as e:
        print(f"Não foi possível editar a mensagem do menu: {e}")
    try:
        await cb.message.delete()
    except Exception:
        pass
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

@dp.message(Command("catalogo_admin"))
async def cmd_catalogo_admin(m):
    """Diagnóstico somente de leitura do catálogo e do arquivo SQLite ativo."""
    if not m.from_user or m.from_user.id != ADMIN_ID:
        return
    try:
        async with aiosqlite.connect(DB) as db:
            cur = await db.execute(
                "SELECT id, nome, cat, preco, link FROM jogos ORDER BY nome COLLATE NOCASE"
            )
            rows = await cur.fetchall()

        categorias_validas = set(CATS) | set(EMULADORES) | {"gratis", "dashboards"}
        sem_link = sum(1 for row in rows if not (row[4] or "").strip())
        cats_invalidas = sum(1 for row in rows if row[2] not in categorias_validas)
        linhas = [
            "🔎 DIAGNÓSTICO DO CATÁLOGO",
            f"Itens encontrados: {len(rows)}",
            f"Sem link cadastrado: {sem_link}",
            f"Categoria não reconhecida: {cats_invalidas}",
            f"Banco em uso: {os.path.abspath(DB)}",
            "",
            "ITENS (link indicado apenas como SIM/NÃO):"
        ]
        for jid, nome, cat, preco, link in rows[:35]:
            tem_link = "SIM" if (link or "").strip() else "NÃO"
            linhas.append(
                f"• {nome} | id={jid} | cat={cat} | R$ {float(preco or 0):.2f} | link={tem_link}"
            )
        if len(rows) > 35:
            linhas.append(f"... e mais {len(rows) - 35} itens.")
        if not rows:
            linhas.append("O banco consultado não contém itens.")
        await m.answer("\n".join(linhas))
    except Exception as e:
        print(f"Erro no comando administrativo /catalogo_admin: {e}")
        await m.answer("⚠️ Não consegui consultar o catálogo. Verifique os registros do serviço.")

@dp.message(Command("saude"))
@dp.message(Command("status"))
async def cmd_saude(m):
    # Comando restrito ao administrador: diagnóstico sem expor credenciais.
    if m.from_user.id != ADMIN_ID:
        return
    try:
        async with aiosqlite.connect(DB) as db:
            res = await db.execute(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN preco > 0 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN preco = 0 THEN 1 ELSE 0 END) FROM jogos"
            )
            total, pagos, gratuitos = await res.fetchone()
            res = await db.execute("SELECT st, COUNT(*) FROM pedidos GROUP BY st")
            estados = dict(await res.fetchall())

        segundos = max(0, int(time.monotonic() - START_TIME))
        dias, resto = divmod(segundos, 86400)
        horas, resto = divmod(resto, 3600)
        minutos = resto // 60
        if dias:
            uptime = f"{dias}d {horas}h {minutos}min"
        elif horas:
            uptime = f"{horas}h {minutos}min"
        else:
            uptime = f"{minutos}min"

        total = total or 0
        pagos = pagos or 0
        gratuitos = gratuitos or 0
        pendentes = estados.get("pending", 0)
        em_entrega = estados.get("delivering", 0)
        pix = "configurado" if MP_KEY else "não configurado"
        persistencia = "GitHub configurado" if GITHUB_CATALOG_TOKEN else "PENDENTE (SQLite temporário)"

        texto = (
            "🩺 **Saúde da X360 TECH BR**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 Processo do bot: ativo\n"
            f"⏱️ Tempo desde a última inicialização: {uptime}\n"
            f"🎮 Itens no catálogo: {total}\n"
            f"💰 Itens pagos: {pagos}\n"
            f"🎁 Itens gratuitos: {gratuitos}\n"
            f"🧾 Pedidos aguardando pagamento: {pendentes}\n"
            f"📦 Pedidos em entrega: {em_entrega}\n"
            f"💳 Mercado Pago: {pix}\n"
            f"🗃️ Persistência: {persistencia}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await m.answer(texto, parse_mode="Markdown")
    except Exception as e:
        print(f"Erro no comando administrativo /saude: {e}")
        await m.answer(
            "⚠️ Não consegui consultar todos os indicadores agora. "
            "Verifique os registros do serviço."
        )

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
    await safe_edit(c, f"📂 Categoria: **{CATS.get(cat, EMULADORES.get(cat, cat))}**\n\nEnvie o preco (ex: `10.00`):", cancel_kb)

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
    salvo = await persistir_catalogo()
    res = f"✅ **Jogo Cadastrado!**\n\n🎮 {data['nome']}\n📂 {CATS.get(data['cat'], EMULADORES.get(data['cat'], data['cat']))}\n💰 R$ {data['preco']:.2f}"
    if salvo:
        res += "\n\n☁️ Catálogo salvo no GitHub."
    else:
        res += "\n\n⚠️ **Catálogo ainda NÃO protegido contra reinicializações.** Não cadastre em lote até configurar a persistência."
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
    salvo = await persistir_catalogo()
    aviso = "\n☁️ Salvo no GitHub." if salvo else "\n⚠️ Ainda não salvo no GitHub; não cadastre em lote."
    await m.answer(f"⚡ **Cadastrado:** {nome} (R$ {val:.2f})" + aviso, reply_markup=kb_inicio(), parse_mode="Markdown")

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
    salvo = await persistir_catalogo()
    aviso = "\\n☁️ Salvo no GitHub." if salvo else "\\n⚠️ Ainda não salvo no GitHub; não cadastre em lote."
    await m.answer(f"✅ Cadastrado: **{p[1]}**" + aviso, parse_mode="Markdown")

@dp.message(CommandStart())
async def cmd_st(m):
    try:
        await m.delete()
    except Exception:
        pass

    # Links da vitrine abrem o produto correspondente no bot.
    partes = (m.text or "").split(maxsplit=1)
    payload = partes[1].strip() if len(partes) > 1 else ""
    if payload.startswith("item_"):
        jid = payload[5:]
        async with aiosqlite.connect(DB) as db:
            res = await db.execute("SELECT nome, preco, desc, cat FROM jogos WHERE id = ?", (jid,))
            row = await res.fetchone()
        if row:
            nome, preco, descricao, cat = row
            if float(preco) == 0:
                texto = f"🎮 **{nome}**\n\n{descricao or 'Conteúdo gratuito.'}\n\n**Preço:** GRÁTIS"
                teclado = IKM(inline_keyboard=[
                    [btn("🎁 Receber conteúdo", cb=f"getfree_{jid}", s="success")],
                    [btn("🛍️ Ver catálogo", cb="menu_cat")],
                    [btn("⌂ Início", cb="voltar_ini")]
                ])
            else:
                texto = f"🎮 **{nome}**\n\n{descricao or 'Jogo para Xbox 360.'}\n\n**Categoria:** {CATS.get(cat, cat)}\n**Preço:** R$ {float(preco):.2f}"
                teclado = IKM(inline_keyboard=[
                    [btn(f"Comprar via Pix · R$ {float(preco):.2f}", cb=f"pix_{jid}", s="success")],
                    [btn("🛍️ Ver catálogo", cb="menu_cat")],
                    [btn("⌂ Início", cb="voltar_ini")]
                ])
            await m.answer(texto, reply_markup=teclado, parse_mode="Markdown")
            return

    await m.answer(TXT_INI, reply_markup=kb_inicio(), parse_mode="Markdown")

async def executar_busca(m, termo):
    termo = (termo or "").strip()
    if not termo:
        return await m.answer("Digite o nome do jogo para pesquisar.")
    async with aiosqlite.connect(DB) as db:
        c = await db.execute(
            "SELECT id, nome, preco FROM jogos WHERE nome LIKE ? ORDER BY nome COLLATE NOCASE LIMIT 8",
            (f"%{termo}%",)
        )
        rows = await c.fetchall()
    if not rows:
        return await m.answer(
            f"🔎 Não encontrei jogos com o nome {termo}.\n\nTente outro nome ou confira a escrita.",
            reply_markup=IKM(inline_keyboard=[[btn("🔎 Buscar outro jogo", cb="ajuda_b")],
                                             [btn("◀️ Voltar ao início", cb="voltar_ini")]])
        )
    b = []
    for jid, nome, preco in rows:
        valor = "GRÁTIS" if float(preco) == 0 else f"R$ {float(preco):.2f}"
        b.append([btn(f"🎮 {nome} - {valor}", cb=f"info_{jid}", s="success")])
    b.append([btn("🔎 Buscar outro jogo", cb="ajuda_b")])
    b.append([btn("◀️ Voltar ao início", cb="voltar_ini")])
    await m.answer(f"🔎 Resultados para: {termo}", reply_markup=IKM(inline_keyboard=b))

@dp.message(Command("buscar"))
async def cmd_bs(m, state: FSMContext):
    termo = (m.text or "").partition(" ")[2].strip()
    if not termo:
        await state.set_state(BuscaJogo.termo)
        return await m.answer(
            "🔎 O que você está procurando?\n\n"
            "Digite apenas o nome do jogo, por exemplo: GTA V."
        )
    await state.clear()
    await executar_busca(m, termo)

@dp.message(BuscaJogo.termo, F.text)
async def receber_termo_busca(m, state: FSMContext):
    termo = (m.text or "").strip()
    if termo.startswith("/"):
        await state.clear()
        return await m.answer("Busca cancelada. Para pesquisar, clique em Buscar no menu.")
    await state.clear()
    await executar_busca(m, termo)

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

@dp.callback_query(F.data == "menu_emu")
async def cb_menu_emu(c):
    await c.answer()
    botoes = []
    itens = list(EMULADORES.items())
    for i in range(0, len(itens), 2):
        linha = [btn(itens[i][1], cb=f"e_{itens[i][0]}_1", s="success")]
        if i + 1 < len(itens):
            linha.append(btn(itens[i + 1][1], cb=f"e_{itens[i + 1][0]}_1", s="success"))
        botoes.append(linha)
    botoes.append([btn("◀️ Voltar ao início", cb="voltar_ini")])
    await safe_edit(c, "🕹️ **Emuladores e consoles clássicos**\n\nEscolha um sistema para ver os itens disponíveis:", IKM(inline_keyboard=botoes))

@dp.callback_query(F.data.startswith("e_"))
async def cb_lista_emulador(c):
    partes = c.data.split("_")
    try:
        pg = int(partes[-1])
    except (ValueError, IndexError):
        await c.answer("Opção inválida.", show_alert=True)
        return
    ck = "_".join(partes[1:-1])
    if ck not in EMULADORES:
        await c.answer("Sistema não encontrado.", show_alert=True)
        return
    await c.answer()
    mk, tot = await kb_lista(ck, pg, prefix="e")
    t = f"🕹️ **{EMULADORES[ck]}**" if tot > 0 else f"🕹️ **{EMULADORES[ck]}**\n\n_Catálogo vazio por enquanto._"
    await safe_edit(c, t, mk)

@dp.callback_query(F.data.startswith("c_"))
async def cb_jc(c):
    # Categorias podem conter underscores, como "mundo_aberto".
    try:
        ck, pg_txt = c.data[2:].rsplit("_", 1)
        pg = int(pg_txt)
    except (ValueError, IndexError):
        await c.answer("Categoria inválida.", show_alert=True)
        return
    if ck not in CATS or pg < 1:
        await c.answer("Categoria ou página inválida.", show_alert=True)
        return
    await c.answer()
    mk, tot = await kb_lista(ck, pg)
    nom = CATS[ck]
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
    v = "menu_desb" if ck == "gratis" else ("menu_dash" if ck == "dashboards" else (f"e_{ck}_1" if ck in EMULADORES else f"c_{ck}_1"))
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
        res = await db.execute("SELECT nome, link, preco FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        return
    n, link, preco = row
    if float(preco) > 0:
        await c.answer("Este item é pago. Use o botão de compra via Pix.", show_alert=True)
        return
    if not link or not link.strip():
        await c.message.answer(f"⚠️ O link de {n} está temporariamente indisponível. Nenhum arquivo foi enviado.")
        return
    await c.message.answer(f"📦 A preparar a entrega de: **{n}**...")
    await entregar_conteudo(c.from_user.id, link, n)

@dp.callback_query(F.data.startswith("pix_"))
async def cb_px(c):
    jid = c.data[4:]
    if sdk is None:
        await c.answer("Pagamentos indisponíveis no momento.", show_alert=True)
        return
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT nome, preco, link FROM jogos WHERE id = ?", (jid,))
        row = await res.fetchone()
    if not row:
        await c.answer("Jogo não encontrado.", show_alert=True)
        return
    n, pr, link = row
    if float(pr) <= 0:
        await c.answer("Este item não precisa de pagamento.", show_alert=True)
        return
    if not link or not link.strip():
        await c.answer("O link deste jogo ainda não está cadastrado. Nenhum Pix foi gerado.", show_alert=True)
        return
    await c.answer("Gerando Pix...")
    try:
        if c.message.photo:
            await c.message.edit_caption(caption="⏳ Conectando ao Mercado Pago...", reply_markup=None)
        else:
            await c.message.edit_text("⏳ Conectando ao Mercado Pago...")
    except Exception:
        pass
    pdata = {
        "transaction_amount": float(pr),
        "description": f"X360 - {n}",
        "payment_method_id": "pix",
        "payer": {"email": f"c{c.from_user.id}@gmail.com", "first_name": c.from_user.first_name or "Gamer"}
    }
    try:
        response = (await asyncio.to_thread(sdk.payment().create, pdata)).get("response", {})
        pid = response["id"]
        px = response["point_of_interaction"]["transaction_data"]["qr_code"]
    except Exception as e:
        print(f"Erro ao gerar Pix para {jid}: {e}")
        erro = "Não foi possível gerar o Pix agora. Tente novamente em instantes."
        try:
            if c.message.photo:
                await c.message.edit_caption(caption=f"❌ {erro}", reply_markup=None)
            else:
                await c.message.edit_text(f"❌ {erro}")
        except Exception:
            await c.message.answer(f"❌ {erro}")
        return
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO pedidos VALUES (?, ?, ?, 'pending')", (pid, c.from_user.id, jid))
        await db.commit()
    qr = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={urllib.parse.quote(px)}"
    kb = IKM(inline_keyboard=[
        [btn("🟢 Já paguei — verificar", cb=f"chk_{pid}")],
        [btn("◀️ Voltar ao início", cb="voltar_ini")]
    ])
    try:
        await c.message.delete()
    except Exception:
        pass
    await c.message.answer_photo(
        photo=qr,
        caption=f"🎮 **{n}**\n💰 R$ {float(pr):.2f}\n\n`{px}`",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("chk_"))
async def cb_ck(c):
    if sdk is None:
        await c.answer("Pagamentos indisponíveis no momento.", show_alert=True)
        return
    try:
        pid = int(c.data[4:])
    except (ValueError, TypeError):
        await c.answer("Pedido inválido.", show_alert=True)
        return

    # Conferir a titularidade antes de consultar ou liberar qualquer pedido.
    async with aiosqlite.connect(DB) as db:
        row = await (await db.execute(
            "SELECT uid, jid, st FROM pedidos WHERE pid = ?", (pid,)
        )).fetchone()
    if not row or row[0] != c.from_user.id:
        await c.answer("Este pedido não pertence à sua conta.", show_alert=True)
        return
    if row[2] == "delivered":
        await c.answer("Este pedido já foi entregue.", show_alert=True)
        return
    if row[2] == "delivering":
        await c.answer("A entrega já está em andamento. Aguarde.", show_alert=True)
        return

    try:
        payment = (await asyncio.to_thread(sdk.payment().get, pid)).get("response", {})
    except Exception as e:
        print(f"Erro ao consultar pagamento {pid}: {e}")
        await c.answer("Não consegui consultar o Pix. Tente novamente.", show_alert=True)
        return
    if payment.get("status") != "approved":
        await c.answer("O Pix ainda não foi confirmado. Aguarde e tente novamente.", show_alert=True)
        return

    async with aiosqlite.connect(DB) as db:
        await db.execute("BEGIN IMMEDIATE")
        order = await (await db.execute(
            "SELECT uid, jid, st FROM pedidos WHERE pid = ?", (pid,)
        )).fetchone()
        if not order or order[0] != c.from_user.id:
            await db.rollback()
            await c.answer("Pedido não encontrado para sua conta.", show_alert=True)
            return
        if order[2] == "delivered":
            await db.rollback()
            await c.answer("Este pedido já foi entregue.", show_alert=True)
            return
        if order[2] != "pending":
            await db.rollback()
            await c.answer("A entrega já está em andamento. Aguarde.", show_alert=True)
            return
        item = await (await db.execute(
            "SELECT nome, link FROM jogos WHERE id = ?", (order[1],)
        )).fetchone()
        if not item or not item[1] or not item[1].strip():
            await db.rollback()
            await c.answer("O link do item não está disponível. Fale com o suporte.", show_alert=True)
            return
        nome, link = item
        await db.execute("UPDATE pedidos SET st = 'delivering' WHERE pid = ? AND st = 'pending'", (pid,))
        await db.commit()

    await c.answer("Pagamento confirmado. Preparando a entrega...")
    try:
        ok = await entregar_conteudo(c.from_user.id, link, nome)
    except Exception as e:
        print(f"Falha na entrega do pedido {pid}: {e}")
        ok = False
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE pedidos SET st = ? WHERE pid = ? AND st = 'delivering'",
            ("delivered" if ok else "pending", pid)
        )
        await db.commit()
    if ok:
        await c.message.answer(f"🎉 **Pagamento confirmado!**\n\nA entrega de **{nome}** foi concluída ou o link foi enviado.")
    else:
        await c.message.answer("⚠️ O pagamento foi confirmado, mas a entrega não foi concluída. Tente verificar novamente ou fale com o suporte.")

@dp.callback_query(F.data == "voltar_ini")
async def cb_vi(c):
    await c.answer()
    await safe_edit(c, TXT_INI, kb_inicio())

@dp.callback_query(F.data == "ajuda_b")
async def cb_ab(c, state: FSMContext):
    await c.answer()
    await state.set_state(BuscaJogo.termo)
    await safe_edit(
        c,
        "🔎 Buscar jogo\n\n"
        "Digite apenas o nome do jogo que você procura.\n"
        "Exemplos: GTA V ou FIFA 19.\n\n"
        "Não precisa digitar nenhum comando.",
        IKM(inline_keyboard=[[btn("❌ Cancelar busca", cb="cancelar_busca")]])
    )

@dp.callback_query(F.data.startswith("tut_"))
async def cb_ti(c):
    await c.answer()
    paginas = {
        "tut_inst": {
            "titulo": "📘 **Tutorial de instalação — visão geral**",
            "texto": "Vamos por etapas! Antes de começar, confirme que o jogo é compatível com seu Xbox 360 desbloqueado e mantenha uma cópia dos arquivos originais.\n\n**Você vai precisar de:**\n• Um pendrive ou HD USB com espaço suficiente.\n• Os arquivos do jogo já extraídos, quando necessário.\n• Uma dashboard, como Aurora ou Nexus, configurada no console.\n\n⚠️ Os passos mudam conforme o formato do jogo. Não misture arquivos GOD e XEX.",
            "anterior": None, "proxima": "tut_1", "rotulo": "Começar · 1/4"
        },
        "tut_1": {
            "titulo": "🟢 **Etapa 1 — preparar o USB**",
            "texto": "1. Conecte o pendrive ao computador.\n2. Faça backup de tudo o que deseja guardar: a formatação apaga os dados.\n3. Se for usar FAT32, formate o dispositivo nesse sistema de arquivos. O Windows pode não oferecer FAT32 para unidades grandes; não apague seus dados para tentar contornar isso.\n4. Copie os arquivos do jogo para o USB mantendo a estrutura de pastas indicada para o formato recebido.\n\n**Pronto?** Na próxima etapa, veja como organizar jogos no formato GOD.",
            "anterior": "tut_inst", "proxima": "tut_2", "rotulo": "Próxima · 2/4"
        },
        "tut_2": {
            "titulo": "📦 **Etapa 2 — jogos no formato GOD**",
            "texto": "O formato GOD costuma vir em pastas numeradas e arquivos de dados próprios.\n\n1. Localize a pasta do jogo já preparada no formato GOD.\n2. Copie-a preservando a estrutura de diretórios esperada pelo Xbox 360, normalmente dentro de Content/0000000000000000/.\n3. Não renomeie pastas nem mova arquivos internos sem saber a estrutura exigida pelo jogo.\n\n**Importante:** a pasta Content e o identificador do título precisam estar organizados corretamente; copiar apenas arquivos soltos pode impedir que o jogo apareça.",
            "anterior": "tut_1", "proxima": "tut_3", "rotulo": "Próxima · 3/4"
        },
        "tut_3": {
            "titulo": "🎮 **Etapa 3 — jogos no formato XEX**",
            "texto": "XEX normalmente é uma pasta de jogo que contém o executável, muitas vezes chamado default.xex, e outros arquivos.\n\n1. Copie a pasta completa do jogo para uma pasta de jogos, por exemplo Games, no dispositivo USB ou no armazenamento configurado.\n2. Não copie somente o default.xex: os demais arquivos e subpastas podem ser necessários.\n3. No console, abra a Aurora ou a dashboard que você utiliza e configure ou atualize o caminho de busca dos jogos, se necessário.\n\nOs nomes dos menus variam conforme a dashboard e a configuração do console.",
            "anterior": "tut_2", "proxima": "tut_4", "rotulo": "Próxima · 4/4"
        },
        "tut_4": {
            "titulo": "✅ **Etapa 4 — localizar o jogo e resolver problemas**",
            "texto": "Se o jogo não aparecer na dashboard:\n• Confira se a cópia terminou e se a pasta não ficou duplicada ou incompleta.\n• Verifique se o caminho de busca da dashboard inclui a pasta correta.\n• Atualize ou faça uma nova varredura da biblioteca.\n• Confirme se os arquivos correspondem ao formato GOD ou XEX.\n\nSe continuar sem aparecer, não apague nem formate o armazenamento. Confira a estrutura dos arquivos ou peça ajuda antes de alterar a configuração.\n\n🎮 **Tutorial concluído!** Você pode voltar ao início ou consultar outra etapa.",
            "anterior": "tut_3", "proxima": None, "rotulo": None
        }
    }
    pagina = paginas.get(c.data, paginas["tut_inst"])
    botoes = []
    navegacao = []
    if pagina["anterior"]:
        navegacao.append(btn("⬅️ Anterior", cb=pagina["anterior"]))
    if pagina["proxima"]:
        navegacao.append(btn("🟢 " + pagina["rotulo"], cb=pagina["proxima"], s="success"))
    if navegacao:
        botoes.append(navegacao)
    botoes.append([btn("⌂ Menu principal", cb="voltar_ini")])
    await safe_edit(c, pagina["titulo"] + "\n\n" + pagina["texto"], IKM(inline_keyboard=botoes))

@dp.callback_query(F.data == "cancelar_busca")
async def cb_cancelar_busca(c, state: FSMContext):
    await state.clear()
    await c.answer("Busca cancelada.")
    await safe_edit(c, TXT_INI, kb_inicio())

@dp.callback_query(F.data == "noop")
async def cb_np(c):
    await c.answer()

@dp.callback_query()
async def cb_desconhecido(c):
    # Evita que botões antigos ou ainda não implementados fiquem sem resposta.
    await c.answer("Esta opção ainda não está disponível. Volte ao menu e tente outra opção.", show_alert=True)

async def api_jogos(request):
    """Catálogo público da loja visual; retorna somente dados necessários à vitrine."""
    termo = request.query.get("q", "").strip()[:80]
    categoria = request.query.get("cat", "").strip()[:40]
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT id, nome, cat, preco, desc FROM jogos WHERE 1=1"
        args = []
        if termo:
            sql += " AND (nome LIKE ? OR desc LIKE ?)"
            args.extend([f"%{termo}%", f"%{termo}%"])
        if categoria:
            sql += " AND cat = ?"
            args.append(categoria)
        sql += " ORDER BY CASE WHEN preco = 0 THEN 0 ELSE 1 END, nome COLLATE NOCASE LIMIT 300"
        cur = await db.execute(sql, args)
        rows = [dict(row) for row in await cur.fetchall()]
    return web.json_response({"jogos": rows, "categorias": {**CATS, **EMULADORES}}, headers={"Cache-Control": "no-store"})


async def ping(request):
    html = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0d0c">
<title>X360 TECH BR — Loja Xbox 360</title>
<style>
:root{color-scheme:dark;--bg:#0b0d0c;--panel:#141816;--panel2:#1a201c;--line:#2b342e;--text:#f3f6f3;--muted:#9ca79f;--green:#75e39a;--green2:#b0f5c2}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:inherit;text-decoration:none}button,input,select{font:inherit}.shell{max-width:1180px;margin:auto;padding:22px 20px 56px}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:8px 0 24px;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:12px;font-weight:850;letter-spacing:.08em}.mark{width:42px;height:42px;border-radius:12px;background:#20392a;color:var(--green);display:grid;place-items:center;font-size:20px;border:1px solid #355a41}.brand small{display:block;font-size:10px;color:var(--muted);letter-spacing:.18em;font-weight:600;margin-top:1px}
.pill{border:1px solid #34523d;border-radius:999px;color:var(--green2);font-size:12px;padding:8px 12px;white-space:nowrap}
.hero{padding:34px 0 30px;display:grid;grid-template-columns:minmax(0,1fr);align-items:center;gap:20px}.eyebrow{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--green);font-weight:800}
h1{font-size:clamp(36px,6vw,64px);line-height:1.02;letter-spacing:-.045em;margin:14px 0 18px;max-width:650px}h1 span{color:var(--green)}
.intro{color:#aab4ad;max-width:540px;font-size:16px}.hero-art{min-height:230px;border:1px solid var(--line);border-radius:24px;background:linear-gradient(145deg,#17231b,#111715 58%,#16271c);display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
.hero-art:before,.hero-art:after{content:"";position:absolute;border:1px solid #3c6549;border-radius:50%;width:240px;height:240px;right:-20px;top:-75px}.hero-art:after{width:180px;height:180px;right:10px;top:-45px;border-color:#2b4b35}
.console{z-index:1;width:180px;height:100px;border:2px solid #6bc98a;border-radius:38px;background:#0c130f;display:flex;align-items:center;justify-content:space-around;transform:rotate(-8deg);box-shadow:0 16px 50px #0008}
.dpad{width:42px;height:42px;position:relative}.dpad:before,.dpad:after{content:"";position:absolute;background:#8ce9a8;border-radius:3px}.dpad:before{width:13px;height:42px;left:14px}.dpad:after{width:42px;height:13px;top:14px}
.buttons{width:44px;height:44px;position:relative}.buttons i{position:absolute;width:11px;height:11px;border-radius:50%;background:#8ce9a8}.buttons i:nth-child(1){top:0;left:16px}.buttons i:nth-child(2){top:16px;right:0}.buttons i:nth-child(3){bottom:0;left:16px}.buttons i:nth-child(4){top:16px;left:0}
.section-head{display:flex;justify-content:space-between;align-items:end;gap:16px;margin:20px 0 16px}.section-head h2{font-size:24px;letter-spacing:-.03em;margin:4px 0}.section-head p{color:var(--muted);margin:0;font-size:13px}
.tools{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}.search{flex:1;min-width:200px;background:#121613;border:1px solid var(--line);border-radius:12px;padding:13px 15px;color:var(--text);outline:none}.search:focus,select:focus{border-color:#5eaa76}.filter{background:#121613;border:1px solid var(--line);border-radius:12px;padding:12px;color:var(--text);min-width:160px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{min-width:0;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:var(--panel);transition:border-color .18s,transform .18s}.card:hover{border-color:#477b54;transform:translateY(-3px)}
.cover{aspect-ratio:4/3;background:linear-gradient(145deg,#213b2a,#111a14 65%,#203e2c);display:flex;align-items:center;justify-content:center;position:relative;padding:16px;text-align:center;overflow:hidden}.cover:before{content:"";position:absolute;width:160px;height:160px;border:1px solid #8ee8a722;border-radius:50%;right:-50px;top:-50px}.cover:after{content:"";position:absolute;width:110px;height:110px;border:1px solid #8ee8a71a;border-radius:50%;left:-45px;bottom:-55px}.cover .initial{font-size:clamp(20px,2vw,32px);font-weight:900;letter-spacing:-.05em;color:#e3f9e9;text-shadow:0 4px 25px #0007;z-index:1;overflow-wrap:anywhere}.free{position:absolute;top:10px;left:10px;font-size:10px;text-transform:uppercase;letter-spacing:.1em;font-weight:800;background:#d6f8df;color:#15311e;border-radius:6px;padding:5px 7px}
.card-body{padding:14px}.cat{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--green);font-weight:800}.name{font-weight:750;font-size:15px;line-height:1.3;margin:6px 0 14px;min-height:38px;overflow-wrap:anywhere}.card-foot{display:flex;align-items:center;justify-content:space-between;gap:8px}.price{font-size:17px;font-weight:850;white-space:nowrap}.price.free-price{color:var(--green)}.details{border:1px solid #3b5a43;background:#1a2b20;color:#dff9e6;border-radius:9px;padding:8px 10px;font-size:12px;font-weight:750;cursor:pointer}
/* Microinterações suaves nos botões da vitrine e do modal */
.details,.primary,.secondary{transition:transform .18s ease,box-shadow .18s ease,background-color .18s ease,border-color .18s ease;will-change:transform}
.details:hover,.primary:hover,.secondary:hover{transform:translateY(-2px) scale(1.02);box-shadow:0 7px 18px #0005}
.details:hover{background:#25402d;border-color:#75e39a}
.primary:hover{background:#b0f5c2;box-shadow:0 0 0 3px #75e39a22,0 8px 22px #75e39a20}
.secondary:hover{border-color:#75e39a;background:#1c261f}
.details:active,.primary:active,.secondary:active{transform:translateY(0) scale(.97);box-shadow:none}
.details:focus-visible,.primary:focus-visible,.secondary:focus-visible{outline:2px solid #b0f5c2;outline-offset:3px}
.details,.primary,.secondary{position:relative;overflow:hidden;isolation:isolate}
.click-ripple{position:absolute;border-radius:50%;pointer-events:none;background:rgba(142,232,167,.32);transform:scale(0);animation:button-ripple .58s ease-out forwards;z-index:0}
@keyframes button-ripple{to{transform:scale(18);opacity:0}}
@media(prefers-reduced-motion:reduce){.details,.primary,.secondary{transition:none;will-change:auto}.details:hover,.primary:hover,.secondary:hover,.details:active,.primary:active,.secondary:active{transform:none}.click-ripple{display:none}}
@media(prefers-reduced-motion:reduce){.details,.primary,.secondary{transition:none;will-change:auto}.details:hover,.primary:hover,.secondary:hover,.details:active,.primary:active,.secondary:active{transform:none}}
.status{grid-column:1/-1;text-align:center;border:1px dashed var(--line);border-radius:16px;padding:35px;color:var(--muted)}.footer{margin-top:44px;border-top:1px solid var(--line);padding-top:20px;color:#77837a;font-size:12px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.modal-bg{position:fixed;inset:0;background:#000b;display:none;align-items:center;justify-content:center;padding:20px;z-index:10}.modal-bg.open{display:flex}.modal{width:min(480px,100%);background:#151a16;border:1px solid #354238;border-radius:20px;padding:24px;box-shadow:0 20px 80px #0009}.modal h3{font-size:24px;margin:8px 0}.modal p{color:#b1bbb4;white-space:pre-wrap}.modal-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:22px}.primary{display:inline-block;background:var(--green);color:#102015;border:0;border-radius:10px;padding:12px 16px;font-weight:850;cursor:pointer}.secondary{display:inline-block;background:transparent;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:12px 16px;cursor:pointer}
@media(max-width:900px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.hero{grid-template-columns:1fr .6fr}.hero-art{min-height:190px}.console{transform:scale(.82) rotate(-8deg)}}
@media(max-width:640px){.shell{padding:14px 14px 38px}.top{padding-bottom:16px}.brand{font-size:13px}.pill{font-size:10px;padding:7px 9px}.hero{padding:34px 0 26px;grid-template-columns:1fr}.hero-art{display:none}h1{font-size:42px}.intro{font-size:14px}.section-head h2{font-size:21px}.section-head p{display:none}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.card-body{padding:11px}.name{font-size:13px;min-height:34px}.price{font-size:15px}.details{padding:7px 8px;font-size:11px}.cover{aspect-ratio:1/1}.filter{min-width:130px;flex:1}.search{min-width:100%;}}
</style></head>
<body><main class="shell">
<header class="top"><div class="brand"><div class="mark">X</div><div>X360 TECH BR<small>LOJA DIGITAL XBOX 360</small></div></div><div class="pill">● CATÁLOGO ONLINE</div></header>
<section class="hero"><div><div class="eyebrow">Sua próxima aventura começa aqui</div><h1>Encontre seu próximo <span>jogo.</span></h1><p class="intro">Uma vitrine simples para explorar jogos de Xbox 360, descobrir conteúdos gratuitos e encontrar o que você procura.</p></div></section>
<section><div class="section-head"><div><div class="eyebrow">Seleção da loja</div><h2>Catálogo de jogos</h2><p id="count">Carregando catálogo…</p></div></div>
<div class="tools"><input class="search" id="q" type="search" placeholder="Buscar jogo pelo nome…" aria-label="Buscar jogo"><select class="filter" id="cat" aria-label="Filtrar categoria"><option value="">Todas as categorias</option><option value="gratis">Conteúdos gratuitos</option><option value="dashboards">Dashboards</option></select></div>
<div class="grid" id="games"><div class="status">Carregando jogos…</div></div></section>
<footer class="footer"><span>© X360 TECH BR</span><span>Catálogo digital · GOD / XEX</span><a href="https://t.me/x360techbr_bot">Abrir bot no Telegram ↗</a></footer>
</main>
<div class="modal-bg" id="modal" role="dialog" aria-modal="true" aria-labelledby="modal-name"><div class="modal"><div class="eyebrow" id="modal-cat">DETALHES DO JOGO</div><h3 id="modal-name"></h3><div class="price" id="modal-price"></div><p id="modal-desc"></p><div class="modal-actions"><a class="primary" id="modal-action" href="https://t.me/x360techbr_bot">Continuar no Telegram</a><button class="secondary" id="close">Fechar</button></div></div></div>
<script>
const botUrl="https://t.me/x360techbr_bot";
let allGames=[];
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pretty=s=>String(s||"").replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
function render(){
 const term=document.getElementById("q").value.trim().toLocaleLowerCase("pt-BR");
 const cat=document.getElementById("cat").value;
 const list=allGames.filter(g=>(!cat||g.cat===cat)&&(!term||(g.nome+" "+(g.desc||"")).toLocaleLowerCase("pt-BR").includes(term)));
 document.getElementById("count").textContent=list.length+" item(ns) no catálogo";
 const target=document.getElementById("games");
 if(!list.length){target.innerHTML='<div class="status">Nenhum jogo encontrado. Tente outro nome ou categoria.</div>';return}
 target.innerHTML=list.map(g=>{
  const free=Number(g.preco)===0;
  const initial=esc(String(g.nome||"X360").split(/\s+/).slice(0,2).map(w=>w[0]||"").join("").toUpperCase());
  const price=free?"GRÁTIS":"R$ "+Number(g.preco).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2});
  return '<article class="card"><div class="cover"><span class="initial">'+initial+'</span>'+(free?'<span class="free">Gratuito</span>':'')+'</div><div class="card-body"><div class="cat">'+esc(pretty(g.cat))+'</div><div class="name">'+esc(g.nome)+'</div><div class="card-foot"><div class="price '+(free?'free-price':'')+'">'+price+'</div><button class="details" data-id="'+esc(g.id)+'">Detalhes</button></div></div></article>';
 }).join("");
}
function openDetails(id){
 const g=allGames.find(x=>x.id===id);if(!g)return;
 const free=Number(g.preco)===0;
 document.getElementById("modal-cat").textContent=pretty(g.cat);
 document.getElementById("modal-name").textContent=g.nome;
 document.getElementById("modal-price").textContent=free?"GRÁTIS":"R$ "+Number(g.preco).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2});
 document.getElementById("modal-desc").textContent=g.desc||"Detalhes deste item serão adicionados em breve.";
 document.getElementById("modal-action").href=botUrl+"?start=item_"+encodeURIComponent(g.id);
 document.getElementById("modal-action").textContent=free?"Receber pelo Telegram":"Comprar pelo Telegram";
 document.getElementById("modal").classList.add("open");
}
document.getElementById("games").addEventListener("click",e=>{const b=e.target.closest("[data-id]");if(b)openDetails(b.dataset.id)});
document.addEventListener("pointerdown",e=>{
 const b=e.target.closest(".details,.primary,.secondary");
 if(!b||window.matchMedia("(prefers-reduced-motion: reduce)").matches)return;
 const rect=b.getBoundingClientRect();
 const size=Math.max(rect.width,rect.height)*1.15;
 b.querySelectorAll(".click-ripple").forEach(r=>r.remove());
 const ripple=document.createElement("span");
 ripple.className="click-ripple";
 ripple.style.width=ripple.style.height=size+"px";
 ripple.style.left=(e.clientX-rect.left-size/2)+"px";
 ripple.style.top=(e.clientY-rect.top-size/2)+"px";
 b.appendChild(ripple);
 ripple.addEventListener("animationend",()=>ripple.remove(),{once:true});
});

document.getElementById("q").addEventListener("input",render);
document.getElementById("cat").addEventListener("change",render);
document.getElementById("close").addEventListener("click",()=>document.getElementById("modal").classList.remove("open"));
document.getElementById("modal").addEventListener("click",e=>{if(e.target.id==="modal")e.currentTarget.classList.remove("open")});
fetch("/api/jogos").then(r=>{if(!r.ok)throw Error("API indisponível");return r.json()}).then(data=>{
 allGames=data.jogos||[];
 const select=document.getElementById("cat");
 const existing=new Set(Array.from(select.options).map(o=>o.value));
 Object.entries(data.categorias||{}).forEach(([key,label])=>{if(!existing.has(key)){const o=document.createElement("option");o.value=key;o.textContent=label.replace(/^[^\p{L}\p{N}]+/u,"");select.appendChild(o)}});
 render();
}).catch(()=>{document.getElementById("games").innerHTML='<div class="status">Não foi possível carregar o catálogo agora. Tente novamente em instantes.</div>';document.getElementById("count").textContent="Catálogo indisponível";});
</script></body></html>"""
    return web.Response(text=html, content_type="text/html")



def make_web_app():
    app = web.Application()
    app.router.add_get("/", ping)
    app.router.add_get("/api/jogos", api_jogos)
    app.router.add_get("/healthz", lambda request: web.Response(text="Online!"))
    return app

async def main():
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
