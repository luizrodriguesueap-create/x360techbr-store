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

CATEGORIAS = {
    "gratis": "🎁 Desbloqueios Grátis",
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
        await db.execute("DELETE FROM jogos WHERE categoria = 'gratis' OR id IN ('badavatar', 'rockband', 'vip_total', 'rockband_pack') OR nome LIKE '%VIP%'")
        await db.execute("""
            INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao)
            VALUES 
            ('abadavatar', 'Desbloqueio via AbadAvatar', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Guia e arquivos completos para desbloqueio via AbadAvatar no Xbox 360.'),
            ('rockband', 'Desbloqueio via Rock Band', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Arquivos para desbloqueio via exploit Rock Band no Xbox 360.')
            ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, descricao=excluded.descricao
        """)
        await db.commit()

# ================= MENUS ESTILO LOJA LIMPA =================
def btn(texto, cb_data=None, url=None, estilo="primary"):
    # Aplica o estilo de cor se suportado pelo cliente (success = verde, primary = azul)
    kw = {"text": texto}
    if cb_data: kw["callback_data"] = cb_data
    if url: kw["url"] = url
    try:
        return InlineKeyboardButton(**kw, style=estilo)
    except TypeError:
        return InlineKeyboardButton(**kw)

def kb_inicio():
    return InlineKeyboardMarkup(inline_keyboard=[
        # Destaque Verde (Estilo da imagem)
        [btn("🟢 Desbloqueio via AbadAvatar e Rock Band (Grátis)", cb_data="cat_gratis_1", estilo="success")],
        # Catálogo em Azul
        [btn("🔵 Catálogo Geral de Jogos (GOD / XEX)", cb_data="menu_cat", estilo="primary")],
        [
            btn("🔍 Pesquisar Jogo", cb_data="ajuda_busca", estilo="primary"),
            btn("📖 Como Instalar", cb_data="tutorial_inst", estilo="primary")
        ]
    ])

def kb_categorias():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("💥 Ação", cb_data="cat_acao_1"), btn("🗺️ Aventura", cb_data="cat_aventura_1")],
        [btn("🚗 Corrida", cb_data="cat_corrida_1"), btn("🥊 Luta", cb_data="cat_luta_1")],
        [btn("🎯 FPS", cb_data="cat_fps_1"), btn("🔫 Tiro", cb_data="cat_tiro_1")],
        [btn("⚽ Esportes", cb_data="cat_esportes_1"), btn("🌆 Mundo Aberto", cb_data="cat_mundo_aberto_1")],
        [btn("🧱 Plataforma", cb_data="cat_plataforma_1"), btn("🧟 Terror", cb_data="cat_terror_1")],
        [btn("🧙 RPG", cb_data="cat_rpg_1"), btn("🕺 Kinect", cb_data="cat_kinect_1")],
        [btn("🟢 Desbloqueios Gratuitos", cb_data="cat_gratis_1", estilo="success")],
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
        if preco == 0.0:
            rotulo = "GRÁTIS"
            b.append([btn(f"🟢 {nome} - {rotulo}", cb_data=f"info_{j_id}", estilo="success")])
        else:
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
    texto = "🎮 **X360 TECH BR**\nEscolha uma opção no catálogo abaixo:"
    await m.answer(texto, reply_markup=kb_inicio(), parse_mode="Markdown")

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

# ================= NAVEGAÇÃO SUAVE =================
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
    txt = f"📂 **{nome_cat}**" if total > 0 else f"📂 **{nome_cat}**\n\n_Nenhum jogo cadastrado ainda nesta categoria._"
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
    voltar_cb = f"cat_{cat_key}_1" if cat_key in CATEGORIAS else "menu_cat"

    if preco == 0.0:
        txt = f"🎁 **{nome}** (Grátis)\n\n📝 {desc}"
        b = [
            [btn("🟢 Baixar Agora (Canal VIP)", url=link, estilo="success")],
            [btn("◀️ Voltar à Lista", cb_data=voltar_cb)]
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

@dp.callback_query(F.data.startswith("gerarpix_"))
async def cb_pix(cb: CallbackQuery):
    j_id = cb.data.replace("gerarpix_", "")
    await cb.answer("Gerando Pix...")
    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT nome, preco FROM jogos WHERE id = ?", (j_id,))
        jogo = await c.fetchone()
    if not jogo: return
    nome, preco = jogo
    await cb.message.edit_text("⏳ Conectando ao Mercado Pago...")
    pdata = {
        "transaction_amount": float(preco),
        "description": f"X360 Tech - {nome}",
        "payment_method_id": "pix",
        "payer": {"email": f"c{cb.from_user.id}@gmail.com", "first_name": cb.from_user.first_name or "Gamer", "last_name": "X360"}
    }
    try:
        p = sdk.payment().create(pdata).get("response", {})
        pid = p["id"]
        pix = p["point_of_interaction"]["transaction_data"]["qr_code"]
    except Exception as e:
        await cb.message.edit_text(f"❌ Erro Pix: {e}")
        return
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO pedidos (payment_id, user_id, jogo_id, status) VALUES (?, ?, ?, 'pending')", (pid, cb.from_user.id, j_id))
        await db.commit()
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={urllib.parse.quote(pix)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn("🟢 Já Paguei (Liberar Download)", cb_data=f"check_{pid}", estilo="success")],
        [btn("◀️ Cancelar", cb_data="voltar_inicio")]
    ])
    await cb.message.delete()
    await cb.message.answer_photo(photo=qr_url, caption=f"🎮 **{nome}**\n💰 R$ {preco:.2f}\n\n`{pix}`", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("check_"))
async def cb_check(cb: CallbackQuery):
    await cb.answer("Verificando...")
    pid = int(cb.data.split("_")[1])
    status = sdk.payment().get(pid).get("response", {}).get("status")
    if status == "approved":
        async with aiosqlite.connect(DB_FILE) as db:
            c = await db.execute("SELECT jogo_id, status FROM pedidos WHERE payment_id = ?", (pid,))
            pedido = await c.fetchone()
            if not pedido or pedido[1] == "delivered":
                await cb.answer("Pedido já entregue!", show_alert=True)
                return
            c2 = await db.execute("SELECT nome, link_download FROM jogos WHERE id = ?", (pedido[0],))
            nome, link = await c2.fetchone()
            await db.execute("UPDATE pedidos SET status = 'delivered' WHERE payment_id = ?", (pid,))
            await db.commit()
        await cb.message.answer(f"🎉 **PAGAMENTO CONFIRMADO!**\n\n🎮 {nome}\n📥 {link}", parse_mode="Markdown")
    else:
        await cb.answer("⏳ Pagamento ainda não compensado.", show_alert=True)

@dp.callback_query(F.data == "voltar_inicio")
async def cb_back(cb: CallbackQuery):
    await cb.answer()
    texto = "🎮 **X360 TECH BR**\nEscolha uma opção no catálogo abaixo:"
    try:
        await cb.message.edit_text(texto, reply_markup=kb_inicio(), parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data == "ajuda_busca")
async def cb_ajuda(cb: CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn("◀️ Voltar", cb_data="voltar_inicio")]])
    try:
        await cb.message.edit_text("🔍 **Como Pesquisar:**\nEnvie `/buscar` e o nome do jogo.\n\nExemplo: `/buscar gta` ou `/buscar resident`", reply_markup=kb, parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data == "tutorial_inst")
async def cb_tut(cb: CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn("◀️ Voltar", cb_data="voltar_inicio")]])
    txt = (
        "📖 **Tutorial Rápido (Pendrive / HD):**\n\n"
        "1. Pendrive formatado em FAT32.\n"
        "2. **Formato GOD:** copie para `Content\\0000000000000000`\n"
        "3. **Formato XEX:** copie a pasta com `default.xex` para `Games`\n"
        "4. Abra a Aurora ou Freestyle e aproveite!"
    )
    try:
        await cb.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
    except Exception: pass

@dp.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()

async def handle_ping(r):
    return web.Response(text="Online!")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/healthz", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    await web.TCPSite(runner, "0.0.0.0", port).start()

async def main():
    try:
        await start_webserver()
        await init_db()
        print("🚀 Online!")
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
