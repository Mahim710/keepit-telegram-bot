import asyncio
import os
import io
import tempfile
from aiohttp import web, ClientSession
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import img2pdf
import pymupdf

# ---- CONFIGURATION ----
TOKEN = os.getenv("TOKEN")                       # set in Render env vars, or via "set TOKEN=..."
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")    # Render sets this automatically
PORT = int(os.getenv("PORT", 8080))

ACTIVE_TIMERS = {}
USER_PHOTOS = {}
TEMP_DIR = tempfile.gettempdir()

# ---- START / HELP ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *My Bot* is ready!\n\n"
        "*🍅 Pomodoro Timer:*\n"
        "/pomodoro – 25 min work, 5 min break\n"
        "/pomodoro 50 10 – custom work & break\n"
        "/stop – cancel your timer\n\n"
        "*📄 Image → PDF:*\n"
        "1. Send all your photos\n"
        "2. Send /pdf → get one combined PDF\n"
        "3. /clearpdf → start over\n\n"
        "*🖼 PDF → Image:*\n"
        "Send a PDF file → get each page as an image",
        parse_mode="Markdown"
    )

# ---- POMODORO ----
async def pomodoro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in ACTIVE_TIMERS:
        await update.message.reply_text("⚠️ You already have a timer running. Use /stop first.")
        return

    if context.args:
        try:
            work_min = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Use numbers. Example: /pomodoro 25 5")
            return
        break_min = int(context.args[1]) if len(context.args) > 1 else 5
    else:
        work_min = 25
        break_min = 5

    if work_min < 1 or work_min > 180 or break_min < 1 or break_min > 60:
        await update.message.reply_text("Work: 1-180 min, Break: 1-60 min.")
        return

    msg = await update.message.reply_text(
        f"🍅 *Work session started!* ({work_min} min)\n⏳ {work_min:02d}:00 remaining\n_(/stop to cancel)_",
        parse_mode="Markdown"
    )

    ACTIVE_TIMERS[user_id] = True

    try:
        total = work_min * 60
        start_t = asyncio.get_event_loop().time()
        last = ""
        while True:
            if user_id not in ACTIVE_TIMERS:
                await msg.edit_text("🛑 Timer stopped.", parse_mode="Markdown")
                return
            remaining = total - int(asyncio.get_event_loop().time() - start_t)
            if remaining <= 0:
                break
            m, s = divmod(remaining, 60)
            text = f"🍅 *Work session*\n⏳ {m:02d}:{s:02d} remaining\n_(/stop to cancel)_"
            if text != last:
                try:
                    await msg.edit_text(text, parse_mode="Markdown")
                    last = text
                except Exception:
                    pass
            await asyncio.sleep(0.5)

        await msg.edit_text(
            f"✅ *Work done!* Take a {break_min} min break.\n☕ {break_min:02d}:00\n_(/stop to cancel)_",
            parse_mode="Markdown"
        )

        total = break_min * 60
        start_t = asyncio.get_event_loop().time()
        last = ""
        while True:
            if user_id not in ACTIVE_TIMERS:
                await msg.edit_text("🛑 Timer stopped.", parse_mode="Markdown")
                return
            remaining = total - int(asyncio.get_event_loop().time() - start_t)
            if remaining <= 0:
                break
            m, s = divmod(remaining, 60)
            text = f"☕ *Break time*\n⏳ {m:02d}:{s:02d} remaining\n_(/stop to cancel)_"
            if text != last:
                try:
                    await msg.edit_text(text, parse_mode="Markdown")
                    last = text
                except Exception:
                    pass
            await asyncio.sleep(0.5)

        await msg.edit_text("🔔 *Break over!* Type /pomodoro to start again.", parse_mode="Markdown")

    finally:
        ACTIVE_TIMERS.pop(user_id, None)

async def stop_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ACTIVE_TIMERS:
        ACTIVE_TIMERS.pop(user_id, None)
        await update.message.reply_text("🛑 Timer stopped.")
    else:
        await update.message.reply_text("You don't have any timer running.")

# ---- IMAGE COLLECTION ----
async def collect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in USER_PHOTOS:
        USER_PHOTOS[user_id] = []
    photo = update.message.photo[-1]
    USER_PHOTOS[user_id].append(photo.file_id)

async def create_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_ids = USER_PHOTOS.get(user_id, [])

    if not file_ids:
        await update.message.reply_text("📭 You haven't sent any photos yet. Send some first, then /pdf.")
        return

    status = await update.message.reply_text(f"📄 Creating PDF from {len(file_ids)} photo(s)...")

    tmp_files = []
    pdf_path = None
    try:
        for i, fid in enumerate(file_ids):
            tg_file = await context.bot.get_file(fid)
            path = os.path.join(TEMP_DIR, f"user_{user_id}_{i}.jpg")
            await tg_file.download_to_drive(path)
            tmp_files.append(path)

        pdf_path = os.path.join(TEMP_DIR, f"user_{user_id}_output.pdf")
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(tmp_files))

        with open(pdf_path, "rb") as f:
            await context.bot.send_document(update.effective_chat.id, f, filename="combined.pdf")

        USER_PHOTOS[user_id] = []

        try:
            await status.delete()
        except Exception:
            pass
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")
    finally:
        for p in tmp_files:
            try:
                os.remove(p)
            except Exception:
                pass
        if pdf_path:
            try:
                os.remove(pdf_path)
            except Exception:
                pass

async def clear_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in USER_PHOTOS:
        count = len(USER_PHOTOS[user_id])
        USER_PHOTOS[user_id] = []
        await update.message.reply_text(f"🗑 Cleared {count} collected photo(s).")
    else:
        await update.message.reply_text("You have no collected photos.")

# ---- PDF → IMAGE ----
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    name = (doc.file_name or "").lower()

    if not name.endswith(".pdf"):
        await update.message.reply_text("Please send a *PDF* file, or send photos then /pdf.", parse_mode="Markdown")
        return

    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("PDF too large (max 20 MB).")
        return

    status = await update.message.reply_text("🖼 Converting PDF to images...")
    tmp_pdf = None
    try:
        tg_file = await doc.get_file()
        tmp_pdf = os.path.join(TEMP_DIR, f"{doc.file_unique_id}.pdf")
        await tg_file.download_to_drive(tmp_pdf)

       pdf = pymupdf.open(tmp_pdf)
        total = len(pdf)
        for i, page in enumerate(pdf):
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            await update.message.reply_photo(
                photo=io.BytesIO(img_bytes),
                caption=f"Page {i+1}/{total}"
            )
        pdf.close()

        try:
            await status.delete()
        except Exception:
            pass
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")
    finally:
        if tmp_pdf:
            try:
                os.remove(tmp_pdf)
            except Exception:
                pass

# ---- WEB SERVER (for Render) ----
async def health(request):
    return web.Response(text="Bot is alive")

async def keep_alive():
    """Ping our own URL every 14 minutes so Render free tier never sleeps."""
    if not RENDER_URL:
        return
    async with ClientSession() as session:
        while True:
            try:
                async with session.get(RENDER_URL) as resp:
                    pass
            except Exception:
                pass
            await asyncio.sleep(14 * 60)

async def run_web_server():
    web_app = web.Application()
    web_app.router.add_get("/", health)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# ---- MAIN ----
async def main_async():
    await run_web_server()
    asyncio.create_task(keep_alive())

    application = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pomodoro", pomodoro))
    application.add_handler(CommandHandler("stop", stop_timer))
    application.add_handler(CommandHandler("pdf", create_pdf))
    application.add_handler(CommandHandler("clearpdf", clear_pdf))
    application.add_handler(MessageHandler(filters.PHOTO, collect_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot is running...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main_async())
