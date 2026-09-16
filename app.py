import asyncio
import html
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from config import Config
from database import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("emperorfm")

BOT_API = "https://api.telegram.org/bot{}/{}"
FILE_API = "https://api.telegram.org/file/bot{}/{}"
http: httpx.AsyncClient | None = None
poll_task = None
BOT_USERNAME = ""
OFFSET = 0


def api_url(method):
    return BOT_API.format(Config.BOT_TOKEN, method)

async def tg_call(method, payload=None):
    r = await http.post(api_url(method), json=payload or {}, timeout=35)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram API error"))
    return data["result"]

async def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await tg_call("sendMessage", payload)

async def is_member(user_id):
    if not Config.FORCE_SUB_CHANNEL_ID:
        return True
    try:
        m = await tg_call("getChatMember", {"chat_id": Config.FORCE_SUB_CHANNEL_ID, "user_id": user_id})
        return m.get("status") in {"creator", "administrator", "member"}
    except Exception as e:
        log.warning("Force-sub check failed: %s", e)
        return False


def safe_name(name):
    name = os.path.basename(name or "file")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:180] or "file"


def readable(size):
    size = int(size or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    n = 0
    while size >= 1024 and n < len(units)-1:
        size /= 1024
        n += 1
    return f"{size:.2f} {units[n]}"


def media_from_message(msg):
    for key in ("document", "video", "audio"):
        media = msg.get(key)
        if media:
            return key, media
    return None, None

async def handle_start(chat_id, user_id, args):
    global BOT_USERNAME
    if args.startswith("verify_"):
        unique_id = args.split("_", 1)[1]
        if not await is_member(user_id):
            username = Config.FORCE_SUB_CHANNEL_USERNAME
            join_url = f"https://t.me/{username}" if username else None
            rows = []
            if join_url:
                rows.append([{"text": "📢 Join Channel", "url": join_url}])
            rows.append([{"text": "♻️ Try Again", "url": f"https://t.me/{BOT_USERNAME}?start=verify_{unique_id}"}])
            await send_message(chat_id, "<b>⚠️ Please join our required channel first.</b>\n\nThen tap <b>♻️ Try Again</b>.", {"inline_keyboard": rows})
            return
        doc = await db.get_link(unique_id)
        if not doc:
            await send_message(chat_id, "❌ Link expired or invalid.")
            return
        final = f"{Config.BASE_URL}/show/{unique_id}"
        await send_message(chat_id, f"<b>✅ Verification successful!</b>\n\nOpen your link:\n<code>{html.escape(final)}</code>", {"inline_keyboard": [[{"text": "▶ Open Streaming Page", "url": final}]]})
        return

    await send_message(chat_id, "👋 <b>Hello!</b>\n\nSend a file to this bot and it will create a shareable streaming link.")

async def handle_file(msg):
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    if user_id != Config.OWNER_ID:
        # Normal users may upload files; this mirrors the source project's sharing flow.
        pass
    kind, media = media_from_message(msg)
    if not media:
        return

    # Bot API copyMessage stores a copy in the private storage channel.
    copied = await tg_call("copyMessage", {"chat_id": Config.STORAGE_CHANNEL_ID, "from_chat_id": chat_id, "message_id": msg["message_id"]})
    storage_message_id = copied["message_id"]

    file_id = media.get("file_id")
    unique = secrets.token_urlsafe(10)
    await db.save_link(unique, storage_message_id, file_id, media.get("file_name") or "file", media.get("mime_type") or ("video/mp4" if kind == "video" else "audio/mpeg" if kind == "audio" else "application/octet-stream"), media.get("file_size", 0))
    link = f"https://t.me/{BOT_USERNAME}?start=verify_{unique}"
    await send_message(chat_id, "<b>✅ File uploaded.</b>\n\nTap below to get the protected streaming link.", {"inline_keyboard": [[{"text": "🔗 Get Link Now", "url": link}]]})

async def handle_update(update):
    msg = update.get("message")
    if not msg:
        return
    chat = msg.get("chat", {})
    if chat.get("type") != "private":
        return
    user = msg.get("from", {})
    if user.get("is_bot"):
        return
    text = msg.get("text", "") or ""
    if text.startswith("/"):
        command = text.split()[0].split("@", 1)[0].lower()
        args = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
        if command == "/start":
            await handle_start(chat["id"], user["id"], args)
        elif command == "/stats" and user["id"] == Config.OWNER_ID:
            count = await db.links.count_documents({})
            await send_message(chat["id"], f"📊 <b>Registered links:</b> {count}")
        else:
            await send_message(chat["id"], "❌ Unknown command.")
        return
    if media_from_message(msg)[0]:
        try:
            await handle_file(msg)
        except Exception:
            log.exception("File handling failed")
            await send_message(chat["id"], "❌ File processing failed. Please try again.")

async def poll_updates():
    global OFFSET, BOT_USERNAME
    me = await tg_call("getMe")
    BOT_USERNAME = me["username"]
    log.info("Bot started: @%s", BOT_USERNAME)
    while True:
        try:
            updates = await tg_call("getUpdates", {"offset": OFFSET, "timeout": 25, "allowed_updates": ["message"]})
            for update in updates:
                OFFSET = update["update_id"] + 1
                try:
                    await handle_update(update)
                except Exception:
                    log.exception("Update failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Polling error")
            await asyncio.sleep(3)

@asynccontextmanager
async def lifespan(app):
    global http, poll_task
    Config.validate()
    http = httpx.AsyncClient(follow_redirects=True)
    await db.connect()
    poll_task = asyncio.create_task(poll_updates())
    yield
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass
    await db.close()
    await http.aclose()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/show/{unique_id}", response_class=HTMLResponse)
async def show_page(request: Request, unique_id: str):
    doc = await db.get_link(unique_id)
    if not doc:
        raise HTTPException(404, "Link expired or invalid.")
    return templates.TemplateResponse("show.html", {"request": request, "unique_id": unique_id, "file_name": doc.get("file_name", "file"), "file_size": readable(doc.get("file_size", 0)), "is_media": (doc.get("mime_type", "")).startswith(("video/", "audio/"))})

async def telegram_file_path(file_id):
    info = await tg_call("getFile", {"file_id": file_id})
    return info["file_path"]

@app.get("/stream/{unique_id}/{filename:path}")
async def stream_file(request: Request, unique_id: str, filename: str):
    doc = await db.get_link(unique_id)
    if not doc:
        raise HTTPException(404, "Link expired or invalid.")
    # Standard Bot API file download is limited to 20 MB.
    size = int(doc.get("file_size", 0))
    if size > 20 * 1024 * 1024:
        raise HTTPException(413, "This API-only version supports streaming files up to 20 MB. Telegram Bot API download limit is 20 MB.")
    path = await telegram_file_path(doc["file_id"])
    url = FILE_API.format(Config.BOT_TOKEN, path)
    range_header = request.headers.get("range")
    headers = {"Range": range_header} if range_header else {}
    upstream = await http.stream("GET", url, headers=headers, timeout=None).__aenter__()
    if upstream.status_code >= 400:
        await upstream.aclose()
        raise HTTPException(upstream.status_code, "Telegram file download failed.")
    response_headers = {k: v for k, v in upstream.headers.items() if k.lower() in {"content-type", "content-length", "content-range", "accept-ranges"}}
    response_headers["Content-Disposition"] = f'inline; filename="{safe_name(doc.get("file_name"))}"'
    async def body():
        try:
            async for chunk in upstream.aiter_bytes(1024 * 1024):
                yield chunk
        finally:
            await upstream.aclose()
    return StreamingResponse(body(), status_code=206 if range_header else 200, headers=response_headers, media_type=doc.get("mime_type") or "application/octet-stream")

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=Config.PORT)
