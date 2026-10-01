import asyncio
import os
import io
import gc
import zipfile
import tempfile
from aiohttp import web, ClientSession
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import img2pdf
import pymupdf

# ---- CONFIGURATION ----
TOKEN = os.getenv("TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 8080))

ACTIVE_TIMERS = {}
USER_PHOTOS = {}
USER_CONVERTS = {}
USER_PDF_TASKS = {}
TEMP_DIR = tempfile.gettempdir()

PHOTO_PAGE_LIMIT = 20
MAX_TOTAL_PAGES = 200
GC_EVERY = 20
STATUS_EVERY = 25

# ---- START / HELP ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *My Bot* is ready!\n\n"
        "*🍅 Pomodoro Timer:*\n"
        "/pomodoro – 25 min work, 5 min break\n"
        "/stop – cancel your timer\n\n"
        "*📄 Image → PDF:*\n"
        "Send photos → /pdf → get one PDF\n"
        "/clearpdf – reset\n\n"
        "*🖼 PDF → Image:*\n"
        "Send a PDF → get photos or ZIP\n"
        "/stopconvert – cancel conversion",
        parse_mode="Markdown"
    )

# ---- POMODORO ----
async def pomodoro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ACTIVE_TIMERS:
        await update.message.reply_text("⚠️ Timer already running. Use /stop first.")
        return
    if context.args:
        try:
            work_min = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Use numbers. Example: /pomodoro 25 5")
            return
        break_min = int(context.args[1]) if len(context.args) > 1 else 5
    else:
        work_min, break_min = 25, 5

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
            if remaining <= 0: break
            m, s = divmod(remaining, 60)
            text = f"🍅 *Work session*\n⏳ {m:02d}:{s:02d} remaining\n_(/stop to cancel)_"
            if text != last:
                try:
                    await msg.edit_text(text, parse_mode="Markdown")
                    last = text
                except Exception: pass
            await asyncio.sleep(0.5)

        await msg.edit_text(f"✅ *Work done!* Take a {break_min} min break.\n☕ {break_min:02d}:00\n_(/stop to cancel)_", parse_mode="Markdown")
        total = break_min * 60
        start_t = asyncio.get_event_loop().time()
        last = ""
        while True:
            if user_id not in ACTIVE_TIMERS:
                await msg.edit_text("🛑 Timer stopped.", parse_mode="Markdown")
                return
            remaining = total - int(asyncio.get_event_loop().time() - start_t)
            if remaining <= 0: break
            m, s = divmod(remaining, 60)
            text = f"☕ *Break time*\n⏳ {m:02d}:{s:02d} remaining\n_(/stop to cancel)_"
            if text != last:
                try:
                    await msg.edit_text(text, parse_mode="Markdown")
                    last = text
                except Exception: pass
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

# ---- IMAGE → PDF ----
async def collect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in USER_PHOTOS:
        USER_PHOTOS[user_id] = []
    USER_PHOTOS[user_id].append(update.message.photo[-1].file_id)

async def create_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in USER_PDF_TASKS and not USER_PDF_TASKS[user_id].done():
        await update.message.reply_text("⚠️ PDF creation already running. Use /stopconvert to cancel.")
        return
    file_ids = USER_PHOTOS.get(user_id, [])
    if not file_ids:
        await update.message.reply_text("📭 No photos collected. Send photos first, then /pdf.")
        return
    # Clear photos immediately so user can start a new batch if needed
    USER_PHOTOS[user_id] = []
    task = asyncio.create_task(process_image_to_pdf_task(update, context, file_ids))
    USER_PDF_TASKS[user_id] = task

async def process_image_to_pdf_task(update, context, file_ids):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    status = await context.bot.send_message(chat_id, f"📄 Creating PDF from {len(file_ids)} photo(s)...")
    tmp_files = []
    pdf_path = None
    try:
        # Download photos in parallel (10 at a time)
        sem = asyncio.Semaphore(10)
        async def download_one(fid, idx):
            async with sem:
                tg_file = await context.bot.get_file(fid)
                path = os.path.join(TEMP_DIR, f"user_{user_id}_{idx}.jpg")
                await tg_file.download_to_drive(path)
                return path

        tasks = [download_one(fid, i) for i, fid in enumerate(file_ids)]
        tmp_files = await asyncio.gather(*tasks)

        pdf_path = os.path.join(TEMP_DIR, f"user_{user_id}_output.pdf")
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(tmp_files))

        await status.edit_text("📤 Uploading PDF...")
        with open(pdf_path, "rb") as f:
            await context.bot.send_document(chat_id, f, filename="combined.pdf")
        try: await status.delete()
        except Exception: pass
    except asyncio.CancelledError:
        try: await context.bot.send_message(chat_id, "🛑 PDF creation stopped.")
        except Exception: pass
    except Exception as e:
        try: await status.edit_text(f"❌ Error: {e}")
        except Exception: pass
    finally:
        for p in tmp_files:
            try: os.remove(p)
            except Exception: pass
        if pdf_path:
            try: os.remove(pdf_path)
            except Exception: pass
        USER_PDF_TASKS.pop(user_id, None)
        gc.collect()

async def clear_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in USER_PHOTOS:
        count = len(USER_PHOTOS[user_id])
        USER_PHOTOS[user_id] = []
        await update.message.reply_text(f"🗑 Cleared {count} photo(s).")
    else:
        await update.message.reply_text("No collected photos.")

# ---- PDF → IMAGE ----
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    name = (doc.file_name or "").lower()
    if not name.endswith(".pdf"):
        await update.message.reply_text("Please send a *PDF* file.", parse_mode="Markdown")
        return
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("PDF too large (max 20 MB).")
        return
    user_id = update.effective_user.id
    if user_id in USER_CONVERTS and not USER_CONVERTS[user_id].done():
        await update.message.reply_text("⚠️ Conversion already running. Use /stopconvert.")
        return
    task = asyncio.create_task(convert_pdf_task(update, context, doc))
    USER_CONVERTS[user_id] = task

async def convert_pdf_task(update, context, doc):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    status = await context.bot.send_message(chat_id, "🖼 Preparing conversion...")
    tmp_pdf = None
    zip_path = None
    try:
        tg_file = await doc.get_file()
        tmp_pdf = os.path.join(TEMP_DIR, f"{doc.file_unique_id}.pdf")
        await tg_file.download_to_drive(tmp_pdf)

        pdf = pymupdf.open(tmp_pdf)
        total = len(pdf)

        if total > MAX_TOTAL_PAGES:
            await status.edit_text(f"❌ PDF has *{total} pages*. Limit: *{MAX_TOTAL_PAGES}*.", parse_mode="Markdown")
            pdf.close(); return

        if total <= PHOTO_PAGE_LIMIT:
            await status.edit_text(f"📸 Sending {total} page(s) as photos...")
            for i, page in enumerate(pdf):
                pix = page.get_pixmap(dpi=120)
                await context.bot.send_photo(chat_id, photo=io.BytesIO(pix.tobytes("png")), caption=f"Page {i+1}/{total}")
                pix = None
                if (i + 1) % GC_EVERY == 0: gc.collect()
                await asyncio.sleep(0.4)
        else:
            await status.edit_text(f"📦 PDF has {total} pages. Building ZIP...\n_(/stopconvert to cancel)_", parse_mode="Markdown")
            zip_path = os.path.join(TEMP_DIR, f"{doc.file_unique_id}.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, page in enumerate(pdf):
                    pix = page.get_pixmap(dpi=72)
                    zf.writestr(f"page_{i+1:04d}.jpg", pix.tobytes("jpeg"))
                    pix = None
                    if (i + 1) % GC_EVERY == 0: gc.collect()
                    if (i + 1) % STATUS_EVERY == 0:
                        try: await status.edit_text(f"📦 Converting... {i+1}/{total}\n_(/stopconvert to cancel)_", parse_mode="Markdown")
                        except Exception: pass
            await status.edit_text(f"📤 Uploading {total}-page ZIP...")
            with open(zip_path, "rb") as f:
                await context.bot.send_document(chat_id, document=f, filename=f"pages_{total}.zip")

        pdf.close()
        try: await status.delete()
        except Exception: pass
    except asyncio.CancelledError:
        try: await context.bot.send_message(chat_id, "🛑 Conversion stopped.")
        except Exception: pass
    except Exception as e:
        try: await status.edit_text(f"❌ Error: {e}")
        except Exception: pass
    finally:
        if tmp_pdf:
            try: os.remove(tmp_pdf)
            except Exception: pass
        if zip_path:
            try: os.remove(zip_path)
            except Exception: pass
        USER_CONVERTS.pop(user_id, None)
        gc.collect()

async def stop_convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stopped = False
    if user_id in USER_CONVERTS and not USER_CONVERTS[user_id].done():
        USER_CONVERTS[user_id].cancel(); stopped = True
    if user_id in USER_PDF_TASKS and not USER_PDF_TASKS[user_id].done():
        USER_PDF_TASKS[user_id].cancel(); stopped = True
    if stopped:
        await update.message.reply_text("🛑 Stopping...")
    else:
        await update.message.reply_text("Nothing running to stop.")

# ---- WEB SERVER ----
async def health(request): return web.Response(text="Bot is alive")
async def keep_alive():
    if not RENDER_URL: return
    async with ClientSession() as session:
        while True:
            try:
                async with session.get(RENDER_URL) as resp: pass
            except Exception: pass
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
    application = (Application.builder().token(TOKEN).concurrent_updates(True)
                   .read_timeout(30).write_timeout(60).connect_timeout(30).pool_timeout(30).build())
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pomodoro", pomodoro))
    application.add_handler(CommandHandler("stop", stop_timer))
    application.add_handler(CommandHandler("pdf", create_pdf))
    application.add_handler(CommandHandler("clearpdf", clear_pdf))
    application.add_handler(CommandHandler("stopconvert", stop_convert))
    application.add_handler(MessageHandler(filters.PHOTO, collect_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print("Bot is running...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main_async())
