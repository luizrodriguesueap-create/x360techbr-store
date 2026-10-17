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
    "gratis": "🎁 Desbloqueios Gratis",
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

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS jogos (id TEXT PRIMARY KEY, nome TEXT, categoria TEXT, preco REAL, link_download TEXT, descricao TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS pedidos (payment_id INTEGER PRIMARY KEY, user_id INTEGER, jogo_id TEXT, status TEXT)")
        
        # LIMPEZA TOTAL DE ITENS ANTIGOS DA CATEGORIA GRATIS
        await db.execute("DELETE FROM jogos WHERE categoria = 'gratis' OR id = 'vip_total' OR nome LIKE '%VIP%'")
        
        # INSERÇÃO DOS NOMES EXATOS
        await db.execute("""
            INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao)
            VALUES 
            ('abadavatar', 'Desbloqueio via AbadAvatar', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Guia e arquivos completos para o desbloqueio via AbadAvatar no Xbox 360.'),
            ('rockband', 'Desbloqueio via Rock Band', 'gratis', 0.0, 'https://t.me/+SEU_CANAL', 'Arquivos essenciais para o desbloqueio via exploit Rock Band no Xbox 360.')
            ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, descricao=excluded.descricao
        """)
        await db.commit()

def kb_inicio():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Desbloqueio via AbadAvatar e Rock Band", callback_data="cat_gratis_1")],
        [InlineKeyboardButton(text="📂 Catalogo de Jogos (GOD / XEX)", callback_data="menu_cat")],
        [InlineKeyboardButton(text="🔍 Como Pesquisar por Nome", callback_data="ajuda_busca")],
        [InlineKeyboardButton(text="📖 Como Instalar (Tutorial Pendrive)", callback_data="tutorial_inst")]
    ])

def kb_categorias():
    b = [
        [InlineKeyboardButton(text="💥 Acao", callback_data="cat_acao_1"), InlineKeyboardButton(text="🗺️ Aventura", callback_data="cat_aventura_1")],
        [InlineKeyboardButton(text="🚗 Corrida", callback_data="cat_corrida_1"), InlineKeyboardButton(text="🥊 Luta", callback_data="cat_luta_1")],
        [InlineKeyboardButton(text="🎯 FPS", callback_data="cat_fps_1"), InlineKeyboardButton(text="🔫 Tiro", callback_data="cat_tiro_1")],
        [InlineKeyboardButton(text="⚽ Esportes", callback_data="cat_esportes_1"), InlineKeyboardButton(text="🌆 Mundo Aberto", callback_data="cat_mundo_aberto_1")],
        [InlineKeyboardButton(text="🧱 Plataforma", callback_data="cat_plataforma_1"), InlineKeyboardButton(text="🧟 Terror", callback_data="cat_terror_1")],
        [InlineKeyboardButton(text="🧙 RPG", callback_data="cat_rpg_1"), InlineKeyboardButton(text="🕺 Kinect", callback_data="cat_kinect_1")],
        [InlineKeyboardButton(text="🎁 Desbloqueio via AbadAvatar e Rock Band", callback_data="cat_gratis_1")],
        [InlineKeyboardButton(text="🔙 ❮ VOLTAR AO INICIO ❯", callback_data="voltar_inicio")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=b)

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
        txt_p = "GRATIS" if preco == 0.0 else f"R$ {preco:.2f}"
        ico = "🎁" if preco == 0.0 else "🎮"
        b.append([InlineKeyboardButton(text=f"{ico} {nome} | {txt_p}", callback_data=f"info_{j_id}")])

    total_p = max(1, (total + itens - 1) // itens)
    nav = []
    if pagina > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Anterior", callback_data=f"cat_{cat_key}_{pagina - 1}"))
    if total_p > 1:
        nav.append(InlineKeyboardButton(text=f"📄 {pagina}/{total_p}", callback_data="noop"))
    if pagina < total_p:
        nav.append(InlineKeyboardButton(text="Proxima ➡️", callback_data=f"cat_{cat_key}_{pagina + 1}"))
    if nav:
        b.append(nav)

    b.append([InlineKeyboardButton(text="🔙 ❮ VOLTAR AS CATEGORIAS ❯", callback_data="menu_cat")])
    return InlineKeyboardMarkup(inline_keyboard=b), total

@dp.message(Command("novojogo"))
async def cmd_novo_jogo(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    partes = [p.strip() for p in m.text.replace("/novojogo", "").split("|")]
    if len(partes) < 6:
        await m.answer("⚠️ Use: `/novojogo id | Nome | cat | preco | link | desc`", parse_mode="Markdown")
        return
    j_id, nome, cat, preco_str, link, desc = partes[0].lower(), partes[1], partes[2].lower(), partes[3], partes[4], partes[5]
    if cat not in CATEGORIAS:
        await m.answer("❌ Categoria invalida.")
        return
    try:
        preco = float(preco_str.replace(",", "."))
    except ValueError:
        await m.answer("❌ Preco invalido.")
        return
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO jogos (id, nome, categoria, preco, link_download, descricao) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, categoria=excluded.categoria, preco=excluded.preco, link_download=excluded.link_download, descricao=excluded.descricao", (j_id, nome, cat, preco, link, desc))
        await db.commit()
    await m.answer(f"✅ Cadastrado: **{nome}**", parse_mode="Markdown")

@dp.message(CommandStart())
async def cmd_start(m: Message):
    txt = (
        "🎮 **Bem-vindo a X360 TECH BR!**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ **SEU XBOX 360 AINDA VIVE!** ⚡\n\n"
        "Jogos digitais prontos para pendrive ou HD interno.\n"
        "Baixe em alta velocidade sem encurtadores ou virus!\n\n"
        "🟢 Formato GOD / XEX testado para RGH e JTAG\n"
        "🎁 Desbloqueios e utilitarios gratuitos disponiveis\n"
        "📥 Download direto e seguro via Telegram\n"
        "⚡ Pagamento automatizado via Pix com entrega imediata\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 _Escolha uma categoria ou pesquise o seu jogo favorito:_"
    )
    await m.answer(txt, reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.message(Command("buscar"))
async def cmd_buscar(m: Message):
    termo = m.text.replace("/buscar", "").strip()
    if not termo:
        await m.answer("🔍 Envie `/buscar` seguido do nome do jogo.", parse_mode="Markdown")
        return
    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT id, nome, preco FROM jogos WHERE nome LIKE ? LIMIT 8", (f"%{termo}%",))
        jogos = await c.fetchall()
    if not jogos:
        await m.answer("❌ Nenhum jogo encontrado.")
        return
    b = [[InlineKeyboardButton(text=f"🎮 {nome} | R$ {preco:.2f}", callback_data=f"info_{j_id}")] for j_id, nome, preco in jogos]
    b.append([InlineKeyboardButton(text="🔙 ❮ VOLTAR AO INICIO ❯", callback_data="voltar_inicio")])
    await m.answer(f"🔍 Resultados para '{termo}':", reply_markup=InlineKeyboardMarkup(inline_keyboard=b))

@dp.callback_query(F.data == "menu_cat")
async def cb_cat(cb: CallbackQuery):
    await cb.answer("📂 A abrir categorias...")
    try:
        await cb.message.edit_text("📂 **Escolha o genero do jogo:**", reply_markup=kb_categorias(), parse_mode="Markdown")
    except Exception:
        await cb.message.answer("📂 **Escolha o genero do jogo:**", reply_markup=kb_categorias(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def cb_jogos_cat(cb: CallbackQuery):
    partes = cb.data.split("_")
    cat_key = partes[1]
    pagina = int(partes[2])
    nome_cat = CATEGORIAS.get(cat_key, "Categoria")
    await cb.answer(f"A carregar {nome_cat}...")
    markup, total = await kb_jogos(cat_key, pagina)
    txt = f"{nome_cat}\n━━━━━━━━━━━━━━━━━━━\n"
    txt += "⚠️ Ainda nao ha itens nesta categoria." if total == 0 else "Selecione um item para download:"
    try:
        await cb.message.edit_text(txt, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        await cb.message.answer(txt, reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("info_"))
async def cb_info(cb: CallbackQuery):
    j_id = cb.data.replace("info_", "")
    await cb.answer("A carregar detalhes...")
    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT nome, preco, descricao, categoria, link_download FROM jogos WHERE id = ?", (j_id,))
        jogo = await c.fetchone()
    if not jogo:
        await cb.answer("Item nao encontrado.", show_alert=True)
        return
    nome, preco, desc, cat_key, link = jogo
    voltar_cb = f"cat_{cat_key}_1" if cat_key in CATEGORIAS else "menu_cat"

    if preco == 0.0:
        txt = f"🎁 **{nome}** (Gratuito)\n━━━━━━━━━━━━━━━━━━━\n📝 {desc}\n\nToque abaixo para abrir:"
        b = [
            [InlineKeyboardButton(text="📥 ❮ BAIXAR AGORA (CANAL) ❯", url=link)],
            [InlineKeyboardButton(text="🔙 ❮ VOLTAR A LISTA ❯", callback_data=voltar_cb)]
        ]
    else:
        txt = f"🎮 **{nome}**\n━━━━━━━━━━━━━━━━━━━\n📝 {desc}\n💰 R$ {preco:.2f}\n📦 Formato: GOD / XEX"
        b = [
            [InlineKeyboardButton(text=f"⚡ PAGAR R$ {preco:.2f} VIA PIX ⚡", callback_data=f"gerarpix_{j_id}")],
            [InlineKeyboardButton(text="🔙 ❮ VOLTAR A LISTA ❯", callback_data=voltar_cb)]
        ]
    try:
        await cb.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=b), parse_mode="Markdown")
    except Exception:
        await cb.message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=b), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("gerarpix_"))
async def cb_pix(cb: CallbackQuery):
    j_id = cb.data.replace("gerarpix_", "")
    await cb.answer("A gerar Pix...")
    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT nome, preco FROM jogos WHERE id = ?", (j_id,))
        jogo = await c.fetchone()
    if not jogo:
        return
    nome, preco = jogo
    await cb.message.edit_text("⏳ A gerar cobranca Pix...")
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
        [InlineKeyboardButton(text="✅ JA PAGUEI (LIBERAR DOWNLOAD)", callback_data=f"check_{pid}")],
        [InlineKeyboardButton(text="🔙 ❮ CANCELAR E VOLTAR ❯", callback_data="voltar_inicio")]
    ])
    await cb.message.delete()
    await cb.message.answer_photo(photo=qr_url, caption=f"🎮 **{nome}**\n💰 R$ {preco:.2f}\n\n`{pix}`", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("check_"))
async def cb_check(cb: CallbackQuery):
    await cb.answer("A verificar...")
    pid = int(cb.data.split("_")[1])
    status = sdk.payment().get(pid).get("response", {}).get("status")
    if status == "approved":
        async with aiosqlite.connect(DB_FILE) as db:
            c = await db.execute("SELECT jogo_id, status FROM pedidos WHERE payment_id = ?", (pid,))
            pedido = await c.fetchone()
            if not pedido or pedido[1] == "delivered":
                await cb.answer("Pedido ja entregue!", show_alert=True)
                return
            c2 = await db.execute("SELECT nome, link_download FROM jogos WHERE id = ?", (pedido[0],))
            nome, link = await c2.fetchone()
            await db.execute("UPDATE pedidos SET status = 'delivered' WHERE payment_id = ?", (pid,))
            await db.commit()
        await cb.message.answer(f"🎉 **PAGAMENTO CONFIRMADO!**\n\n🎮 {nome}\n📥 {link}", parse_mode="Markdown")
    else:
        await cb.answer("⏳ Pagamento ainda nao compensado.", show_alert=True)

@dp.callback_query(F.data == "voltar_inicio")
async def cb_back(cb: CallbackQuery):
    await cb.answer("A voltar...")
    txt = (
        "🎮 **Bem-vindo a X360 TECH BR!**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ **SEU XBOX 360 AINDA VIVE!** ⚡\n\n"
        "Escolha uma opcao no menu abaixo:"
    )
    try:
        await cb.message.edit_text(txt, reply_markup=kb_inicio(), parse_mode="Markdown")
    except Exception:
        await cb.message.answer(txt, reply_markup=kb_inicio(), parse_mode="Markdown")

@dp.callback_query(F.data == "ajuda_busca")
async def cb_ajuda(cb: CallbackQuery):
    await cb.answer("Ajuda...")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 ❮ VOLTAR AO INICIO ❯", callback_data="voltar_inicio")]])
    await cb.message.edit_text("🔍 Envie `/buscar` e o nome do jogo.\nExemplo: `/buscar halo`", reply_markup=kb)

@dp.callback_query(F.data == "tutorial_inst")
async def cb_tut(cb: CallbackQuery):
    await cb.answer("Tutorial...")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 ❮ VOLTAR AO INICIO ❯", callback_data="voltar_inicio")]])
    await cb.message.edit_text("📖 **Tutorial:**\n• Pendrive FAT32\n• GOD em Content/0000000000000000\n• XEX em Games", reply_markup=kb)

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
