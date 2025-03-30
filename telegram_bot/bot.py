import os
import json
import tempfile
import logging
import asyncio
import signal  # Import the signal module
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from transcriber import transcribe_audio, write_transcripts

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Maximum allowed file size (in bytes)
MAX_FILE_SIZE = 300 * 1024 * 1024  # 300 MB

# Mapping of language selection to model directory paths (mounted via docker volumes)
MODEL_PATHS = {
    "fa": "/models/fa_model",  # Persian model volume mount
    "en": "/models/en_model",  # English model volume mount
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! لطفاً یک فایل صوتی یا ویدیویی برای تبدیل ارسال کنید.")

async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE, file_type: str, file_path: str):
    """Ask the user to choose the language for transcription."""
    keyboard = [
        [
            InlineKeyboardButton("فارسی", callback_data=f"fa|{file_type}|{file_path}"),
            InlineKeyboardButton("انگلیسی", callback_data=f"en|{file_type}|{file_path}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("لطفاً زبان فایل را انتخاب کنید:", reply_markup=reply_markup)

async def process_file(file_path: str, lang: str, file_type: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the file: convert to required WAV, run transcription, and send result."""
    chat_id = update.effective_chat.id
    progress_message = await context.bot.send_message(chat_id, "0% - شروع پردازش فایل")
    try:
        # 1. Convert file to WAV mono 16k (using ffmpeg asynchronously)
        wav_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        await progress_message.edit_text("20% - در حال تبدیل فایل با ffmpeg")
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", file_path,
            "-ac", "1", "-ar", "16000",
            wav_path
        ]
        proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        await proc.communicate()
        
        # 2. Transcribe the audio using the selected model (run in a thread)
        await progress_message.edit_text("50% - در حال رونویسی فایل")
        model_path = MODEL_PATHS.get(lang)
        results = await asyncio.to_thread(transcribe_audio, model_path, wav_path)
        
        # Write transcripts (temporary files)
        txt_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
        srt_file = tempfile.NamedTemporaryFile(suffix=".srt", delete=False).name
        await asyncio.to_thread(write_transcripts, results, txt_file, srt_file)
        
        # 3. Prepare result based on file type
        if file_type in ["voice", "audio"]:
            with open(txt_file, "r", encoding="utf-8") as f:
                raw_text = f.read().strip()
            await progress_message.edit_text("100% - پردازش به پایان رسید")
            await context.bot.send_message(chat_id, f"متن رونویسی:\n{raw_text}")
        elif file_type == "video":
            merged_path = tempfile.NamedTemporaryFile(suffix=".mkv", delete=False).name
            await progress_message.edit_text("80% - در حال ادغام زیرنویس با ویدیو")
            merge_cmd = [
                "ffmpeg", "-y", "-i", file_path, "-vf", f"subtitles={srt_file}",
                merged_path
            ]
            proc = await asyncio.create_subprocess_exec(*merge_cmd)
            await proc.communicate()
            await progress_message.edit_text("100% - پردازش به پایان رسید")
            await context.bot.send_video(chat_id, video=open(merged_path, "rb"))
        else:
            await context.bot.send_message(chat_id, "نوع فایل پشتیبانی نمی‌شود.")
    except Exception as e:
        logger.exception("Error processing file")
        await context.bot.send_message(chat_id, f"خطا در پردازش فایل: {e}")
    finally:
        # Clean up temporary files
        for f in [wav_path, txt_file, srt_file]:
            try:
                os.remove(f)
            except Exception:
                pass
        await progress_message.delete()

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text("اندازه فایل بیش از 300 مگابایت است.")
        return

    file_type = document.mime_type.split("/")[0]
    file = await document.get_file()
    # Use document.file_name if available; otherwise, use document.file_id with a default extension.
    filename = document.file_name if document.file_name else f"{document.file_id}.ogg"
    file_path = os.path.join(tempfile.gettempdir(), filename)
    # Changed line:
    await file.download_to_drive(custom_path=file_path)
    await ask_language(update, context, file_type, file_path)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    if file.file_size > MAX_FILE_SIZE:
        await update.message.reply_text("اندازه فایل بیش از 300 مگابایت است.")
        return

    file_path = os.path.join(tempfile.gettempdir(), "voice.ogg")
    # Changed line:
    await file.download_to_drive(custom_path=file_path)
    await ask_language(update, context, "voice", file_path)

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if video.file_size > MAX_FILE_SIZE:
        await update.message.reply_text("اندازه فایل بیش از 300 مگابایت است.")
        return

    file = await video.get_file()
    # Use video.file_name if available; otherwise, use video.file_id with a default .mp4 extension.
    filename = video.file_name if video.file_name else f"{video.file_id}.mp4"
    file_path = os.path.join(tempfile.gettempdir(), filename)
    # Changed line:
    await file.download_to_drive(custom_path=file_path)
    await ask_language(update, context, "video", file_path)

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the language selection button callback."""
    query = update.callback_query
    await query.answer()
    try:
        data = query.data.split("|")
        lang, file_type, file_path = data[0], data[1], data[2]
        await query.edit_message_text("در حال پردازش فایل...")
        await process_file(file_path, lang, file_type, update, context)
    except Exception as e:
        logger.exception("Error in language callback")
        await query.edit_message_text(f"خطا: {e}")

async def main():
    # Read BOT TOKEN from environment variable
    token = os.environ.get("BOTTOKEN")
    if not token:
        logger.error("BOTTOKEN not set in environment")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(CallbackQueryHandler(language_callback))

    # Handle graceful shutdown
    async def shutdown(signal, app):
        logger.info(f"Received exit signal {signal.name}...")
        await app.stop()
        await app.shutdown()
        logger.info("Bot stopped.")
        asyncio.get_event_loop().stop()

    loop = asyncio.get_event_loop()
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s, lambda s=s: asyncio.create_task(shutdown(s, app))
        )

    # Start the bot and keep it running until shutdown is triggered
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        logger.info("Bot started.")
        await asyncio.Future()  # Keep the main task alive until interrupted
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()
        await app.shutdown()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    asyncio.run(main())
