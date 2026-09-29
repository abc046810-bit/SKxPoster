import os
import re
import json
import logging
import asyncio
from threading import Thread
from flask import Flask
import httpx
from telegram import (
    Update,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MAIN_OWNER_ID = 8723278238
PORT = int(os.environ.get("PORT", 8080))

DMCA_IMAGE_URL = "https://cdn.phototourl.com/member/2026-09-15-ca86640f-3059-499d-acc8-9d100738e3bc.png"
HOW_TO_DOWNLOAD_URL = "https://t.me/SKxMOVIES/614"

DEFAULT_QUALITIES = [
    "480p",
    "720p HEVC",
    "720p x264",
    "1080p HEVC",
    "1080p x264",
    "HQ-Rip 1080p",
    "HQ 1080p",
]

(
    SELECT_TYPE,
    WAITING_POSTER_URL,
    WAITING_TITLE,
    WAITING_SAMPLE,
    WAITING_TRAILER,
    WAITING_STREAM,
    WAITING_MORE_STREAM,
    WAITING_SEASON,
    WAITING_EPISODE,
    WAITING_SEASON_NUM,
    QUALITY_MENU,
    WAITING_SIZE,
    WAITING_LINK1,
    WAITING_LINK2,
    WAITING_NEW_QUALITY,
    WAITING_SCREENSHOTS,
    WAITING_HASHTAGS,
    CONFIRM_POST,
) = range(18)

# Bulk mode states (separate conversation)
BULK_POSTER, BULK_TEXT, BULK_CONFIRM = range(18, 21)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ADMINS_FILE = "admins.json"
CHANNEL_FILE = "channel.json"


def load_channel():
    """Returns channel id (int or str like @username) or None."""
    if os.path.exists(CHANNEL_FILE):
        try:
            with open(CHANNEL_FILE, "r") as f:
                data = json.load(f)
                return data.get("channel_id")
        except Exception:
            pass
    return None


def save_channel(channel_id):
    with open(CHANNEL_FILE, "w") as f:
        json.dump({"channel_id": channel_id}, f, indent=2)


def clear_channel():
    if os.path.exists(CHANNEL_FILE):
        try:
            os.remove(CHANNEL_FILE)
        except Exception:
            pass


def load_admins():
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("admins", []))
        except Exception:
            pass
    return set()


def save_admins(admins_set):
    with open(ADMINS_FILE, "w") as f:
        json.dump({"admins": list(admins_set)}, f, indent=2)


ADMINS = load_admins()
ADMINS.add(MAIN_OWNER_ID)


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS or user_id == MAIN_OWNER_ID


# ================== HELPERS ==================
def get_user_data(context: ContextTypes.DEFAULT_TYPE):
    if "post" not in context.user_data:
        context.user_data["post"] = {
            "poster": None,
            "screenshots": [],
            "type": None,
            "title": None,
            "sample": None,
            "trailer": None,
            "streams": [],
            "season": None,
            "episode": None,
            "seasons": {},
            "qualities": {q: {"size": None, "links": []} for q in DEFAULT_QUALITIES},
            "current_quality": None,
            "current_season": None,
            "hashtags": None,
        }
    if "to_delete" not in context.user_data:
        context.user_data["to_delete"] = []
    return context.user_data["post"]


def track(context: ContextTypes.DEFAULT_TYPE, message):
    if message and hasattr(message, "message_id"):
        context.user_data.setdefault("to_delete", []).append(message.message_id)


def reset_post(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("post", None)
    context.user_data.pop("to_delete", None)


def get_current_qualities(post):
    if post["type"] == "webseries" and post.get("current_season"):
        return post["seasons"][post["current_season"]]
    return post["qualities"]


def make_quality_keyboard(post):
    qualities = get_current_qualities(post)
    buttons = []
    row = []
    for q in qualities.keys():
        status = "✅" if qualities[q]["links"] else "⬜"
        row.append(InlineKeyboardButton(f"{status} {q}", callback_data=f"q_{q}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("➕ Add New Quality", callback_data="add_new_quality")])

    if post["type"] == "webseries":
        buttons.append([
            InlineKeyboardButton("✅ Season Done", callback_data="season_done"),
            InlineKeyboardButton("➕ Add Another Season", callback_data="add_another_season"),
        ])
        buttons.append([
            InlineKeyboardButton("🏁 Finish All Seasons", callback_data="finish"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("✅ Finish & Continue", callback_data="finish"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ])
    return InlineKeyboardMarkup(buttons)


def is_image_url(text: str) -> bool:
    text = text.strip().lower()
    if not text.startswith(("http://", "https://")):
        return False
    return any(ext in text for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]) or "image.tmdb.org" in text or "tmdb.org" in text or "phototourl.com" in text


def esc(s: str) -> str:
    if not s:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def safe_html_truncate(html: str, max_len: int = 1000) -> str:
    """Truncate HTML without cutting mid-tag (avoids unclosed start tag errors)."""
    if len(html) <= max_len:
        return html
    cut = html[:max_len]
    # If we cut inside a tag, back up to before '<'
    last_lt = cut.rfind("<")
    last_gt = cut.rfind(">")
    if last_lt > last_gt:
        cut = cut[:last_lt]
    # Close common open tags if needed — simpler: strip trailing incomplete line
    cut = cut.rstrip()
    # Avoid ending with open <a ... without >
    if cut.count("<a ") > cut.count("</a>"):
        # remove last incomplete <a ...>
        idx = cut.rfind("<a ")
        if idx >= 0:
            cut = cut[:idx].rstrip()
    return cut + "\n\n… <i>(preview truncated — final post full hoga)</i>"


def build_preview_caption(post) -> str:
    """
    Short safe preview for long posts (many seasons).
    Full caption only used on final Rich/classic send.
    """
    full = build_legacy_caption(post)
    if len(full) <= 1000:
        return full

    # Compact summary when too long
    lines = []
    lines.append("🎬 <b>TITLE</b>")
    lines.append(f'<b>"{esc(post.get("title") or "")}"</b>')
    lines.append("")

    if post.get("type") == "webseries" and post.get("seasons"):
        season_count = 0
        link_count = 0
        for sn, qualities in post["seasons"].items():
            has = any(q.get("links") for q in qualities.values())
            if has:
                season_count += 1
                for q in qualities.values():
                    link_count += len(q.get("links") or [])
        lines.append(f"📺 <b>Web Series</b> — {season_count} season(s), {link_count} link(s)")
    else:
        qcount = sum(1 for q in post.get("qualities", {}).values() if q.get("links"))
        lcount = sum(len(q.get("links") or []) for q in post.get("qualities", {}).values())
        lines.append(f"📥 <b>{qcount}</b> quality(ies), <b>{lcount}</b> link(s)")

    ss = len(post.get("screenshots") or [])
    if ss:
        lines.append(f"📸 Screenshots: {ss}")

    lines.append("")
    lines.append("<i>Preview shortened (bahut seasons/links).</i>")
    lines.append("<i>Final post mein poora caption + Rich Message jayega.</i>")
    return "\n".join(lines)


# ================== RICH MESSAGE BUILDER ==================
def build_rich_html_and_media(post):
    """
    Professional Rich Message HTML + media bindings.
    """
    media = []
    parts = []

    # ----- Poster -----
    poster = post.get("poster")
    if poster:
        if isinstance(poster, str) and poster.startswith("http"):
            parts.append(f'<img src="{esc(poster)}"/>')
        else:
            media.append({"id": "poster", "media": {"type": "photo", "media": poster}})
            parts.append('<img src="tg://photo?id=poster"/>')
        parts.append("")

    # ----- Title -----
    parts.append("<h2>🎬 TITLE</h2>")
    parts.append(f'<p><b>"{esc(post.get("title") or "")}"</b></p>')

    if post.get("type") == "episode" and post.get("season") and post.get("episode"):
        parts.append(
            f'<p>📺 <b>Season {esc(str(post["season"]))} • Episode {esc(str(post["episode"]))}</b></p>'
        )

    # ----- Sample -----
    if post.get("sample"):
        parts.append("<h3>🎞️ SAMPLE</h3>")
        parts.append(f'<p>🔗 <a href="{esc(post["sample"])}">Watch Sample</a></p>')

    # ----- Trailer -----
    if post.get("trailer"):
        parts.append("<h3>🎥 TRAILER</h3>")
        parts.append(f'<p>🔗 <a href="{esc(post["trailer"])}">Watch Trailer</a></p>')

    # ----- Streams -----
    if post.get("streams"):
        parts.append("<h3>▶️ WATCH / STREAM</h3>")
        for idx, link in enumerate(post["streams"], 1):
            parts.append(f'<p>🔗 <a href="{esc(link)}">Stream Link {idx}</a></p>')
        parts.append("<p><i>⚠️ Online streams may contain ads</i></p>")

    parts.append("<hr/>")

    # ----- Quality Links -----
    parts.append("<h3>📥 ALL QUALITY LINKS</h3>")
    parts.append("<p><i>🔵 Blue text = Clickable Download Link</i></p>")

    has_any_quality = False

    if post.get("type") == "webseries" and post.get("seasons"):
        for season_num in sorted(
            post["seasons"].keys(),
            key=lambda x: int(x) if str(x).isdigit() else 0,
        ):
            qualities = post["seasons"][season_num]
            season_has = any(q.get("links") for q in qualities.values())
            if not season_has:
                continue
            has_any_quality = True
            parts.append(f"<h4>📺 SEASON {esc(str(season_num))}</h4>")
            for q_name, q_data in qualities.items():
                if q_data.get("links"):
                    parts.append(f"<p>🔹 <b>{esc(q_name)}</b></p>")
                    size = q_data.get("size") or "—"
                    parts.append(f"<p>📦 Size: <code>{esc(size)}</code></p>")
                    for idx, link in enumerate(q_data["links"], 1):
                        parts.append(
                            f'<p>🔗 <a href="{esc(link)}">Download Link {idx}</a></p>'
                        )
    else:
        for q_name, q_data in post.get("qualities", {}).items():
            if q_data.get("links"):
                has_any_quality = True
                parts.append(f"<p>🔹 <b>{esc(q_name)}</b></p>")
                size = q_data.get("size") or "—"
                parts.append(f"<p>📦 Size: <code>{esc(size)}</code></p>")
                for idx, link in enumerate(q_data["links"], 1):
                    parts.append(
                        f'<p>🔗 <a href="{esc(link)}">Download Link {idx}</a></p>'
                    )

    if not has_any_quality:
        parts.append("<p><i>No quality links added</i></p>")

    parts.append("<hr/>")

    # ----- Screenshots (expandable + slideshow) with clear hint -----
    screenshots = post.get("screenshots") or []
    if screenshots:
        for i, ss in enumerate(screenshots):
            media.append({"id": f"ss{i}", "media": {"type": "photo", "media": ss}})

        parts.append("<details>")
        parts.append(
            f"<summary>📸 <b>SCREENSHOTS ({len(screenshots)})</b> — Tap to open &amp; swipe</summary>"
        )
        parts.append("<p><i>👆 Click above to expand • Swipe left/right to view all screenshots</i></p>")
        parts.append("<tg-slideshow>")
        for i in range(len(screenshots)):
            parts.append(f'<img src="tg://photo?id=ss{i}"/>')
        parts.append(
            f"<figcaption>Screenshots — {esc(post.get('title') or '')}</figcaption>"
        )
        parts.append("</tg-slideshow>")
        parts.append("</details>")
        parts.append("<hr/>")

    # ----- How to Download -----
    parts.append("<h3>📥 HOW TO DOWNLOAD</h3>")
    parts.append(
        f'<p>🔗 <a href="{HOW_TO_DOWNLOAD_URL}"><b>HOW TO DOWNLOAD MOVIE • WEB SERIES • SHOW BY LINK</b></a></p>'
    )
    parts.append("<hr/>")

    # ----- DMCA -----
    parts.append(
        f'<p>⚖️ <a href="{esc(DMCA_IMAGE_URL)}"><b>DMCA &amp; CONTENT DISCLAIMER</b></a></p>'
    )
    parts.append(
        "<p>We do not host any files. Takedown requests → @SKxMOVIES_RequestBot</p>"
    )

    # ----- Footer -----
    parts.append("<p>🔔 <b>STAY CONNECTED • STAY UPDATED</b> 🚀</p>")

    if post.get("hashtags"):
        parts.append(f"<p>{esc(post['hashtags'])}</p>")

    html = "\n".join(parts)
    return html, media



def build_legacy_caption(post):
    """Fallback plain HTML caption (old style) if Rich Message fails."""
    lines = []
    lines.append("🎬 <b>TITLE</b>")
    lines.append(f'<b>"{esc(post.get("title") or "")}"</b>')
    lines.append("")

    if post.get("type") == "episode" and post.get("season") and post.get("episode"):
        lines.append(
            f"📺 <b>Season {esc(str(post['season']))} • Episode {esc(str(post['episode']))}</b>"
        )
        lines.append("")

    if post.get("sample"):
        lines.append("🎞️ <b>SAMPLE</b>")
        lines.append(f'🔗 <a href="{esc(post["sample"])}">Watch Sample</a>')
        lines.append("")

    if post.get("trailer"):
        lines.append("🎥 <b>TRAILER</b>")
        lines.append(f'🔗 <a href="{esc(post["trailer"])}">Watch Trailer</a>')
        lines.append("")

    if post.get("streams"):
        lines.append("▶️ <b>WATCH / STREAM</b>")
        for idx, link in enumerate(post["streams"], 1):
            lines.append(f'🔗 <a href="{esc(link)}">Stream Link {idx}</a>')
        lines.append("")
        lines.append("⚠️ <i>Online streams may contain ads</i>")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("📥 <b>ALL QUALITY LINKS</b>")
    lines.append("<i>🔵 Blue text = Clickable Link</i>")
    lines.append("")

    if post.get("type") == "webseries" and post.get("seasons"):
        for season_num in sorted(
            post["seasons"].keys(),
            key=lambda x: int(x) if str(x).isdigit() else 0,
        ):
            qualities = post["seasons"][season_num]
            if not any(q.get("links") for q in qualities.values()):
                continue
            lines.append(f"📺 <b>SEASON {esc(str(season_num))}</b>")
            lines.append("")
            for q_name, q_data in qualities.items():
                if q_data.get("links"):
                    lines.append(f"🔹 <b>{esc(q_name)}</b>")
                    size = q_data.get("size") or "—"
                    lines.append(f"📦 Size: <code>{esc(size)}</code>")
                    for idx, link in enumerate(q_data["links"], 1):
                        lines.append(f'🔗 <a href="{esc(link)}">Download Link {idx}</a>')
                    lines.append("")
            lines.append("")
    else:
        for q_name, q_data in post.get("qualities", {}).items():
            if q_data.get("links"):
                lines.append(f"🔹 <b>{esc(q_name)}</b>")
                size = q_data.get("size") or "—"
                lines.append(f"📦 Size: <code>{esc(size)}</code>")
                for idx, link in enumerate(q_data["links"], 1):
                    lines.append(f'🔗 <a href="{esc(link)}">Download Link {idx}</a>')
                lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("📥 <b>HOW TO DOWNLOAD</b>")
    lines.append(
        f'🔗 <a href="{HOW_TO_DOWNLOAD_URL}"><b>HOW TO DOWNLOAD MOVIE • WEB SERIES • SHOW BY LINK</b></a>'
    )
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(
        f'⚖️ <a href="{esc(DMCA_IMAGE_URL)}"><b>DMCA &amp; CONTENT DISCLAIMER</b></a>'
    )
    lines.append("We do not host any files. Takedown → @SKxMOVIES_RequestBot")
    lines.append("")
    lines.append("🔔 <b>STAY CONNECTED • STAY UPDATED</b> 🚀")

    if post.get("hashtags"):
        lines.append("")
        lines.append(esc(post["hashtags"]))

    return "\n".join(lines)


async def send_rich_message(token: str, chat_id: int, html: str, media: list):
    """Call Telegram sendRichMessage via HTTP."""
    payload = {
        "chat_id": chat_id,
        "rich_message": {
            "html": html,
            "skip_entity_detection": False,
        },
    }
    if media:
        payload["rich_message"]["media"] = media

    url = f"https://api.telegram.org/bot{token}/sendRichMessage"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", str(data)))
        return data.get("result")


async def send_final_post(context: ContextTypes.DEFAULT_TYPE, chat_id: int, post: dict, target_chat_id=None):
    """
    Prefer Rich Message. On failure fall back to classic photo/caption/album.
    target_chat_id: if set, post there (channel); else use chat_id.
    """
    dest = target_chat_id if target_chat_id is not None else chat_id
    token = context.bot.token
    html, media = build_rich_html_and_media(post)

    try:
        await send_rich_message(token, dest, html, media)
        logger.info(f"Rich Message sent to {dest}")
        return True
    except Exception as e:
        logger.warning(f"Rich Message failed, falling back to classic: {e}")

    # ----- Fallback: classic -----
    caption = safe_html_truncate(build_legacy_caption(post), 1000)

    poster = post.get("poster")
    screenshots = post.get("screenshots") or []

    try:
        if poster and screenshots:
            media_group = [
                InputMediaPhoto(
                    media=poster,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            ]
            for ss in screenshots:
                media_group.append(InputMediaPhoto(media=ss))
            await context.bot.send_media_group(chat_id=dest, media=media_group)
        elif poster:
            await context.bot.send_photo(
                chat_id=dest,
                photo=poster,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        else:
            await context.bot.send_message(
                chat_id=dest,
                text=caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        return True
    except Exception as e2:
        logger.error(f"Classic send also failed: {e2}")
        # Notify owner in private if channel failed
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Post bhejne mein error: {e2}\n/cancel karke dobara try karo.",
            )
        except Exception:
            pass
        return False



# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Access Denied. This bot is private.")
        return

    text = (
        f"👋 Welcome *{user.first_name}*!\n\n"
        "📌 *Do modes:*\n\n"
        "*1) Step-by-step*\n"
        "Photo bhejo ya `/new`\n"
        "→ Type → Title → Sample/Trailer/Stream\n"
        "→ Qualities → Screenshots → Confirm\n\n"
        "*2) Bulk paste (fast)*\n"
        "`/bulk` → Poster → caption paste → Send\n\n"
        "📢 Channel: `/setchannel @YourChannel`\n\n"
        "*Commands:*\n"
        "`/new`  `/bulk`  `/cancel`\n"
        "`/setchannel`  `/getchannel`  `/removechannel`\n"
        "`/addadmin`  `/removeadmin`  `/admins`\n"
        "`/help`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = (
        "🛠 *SKxPoster — Full Help*\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "*MODE 1 — Step by step*\n"
        "• Photo upload *ya* `/new`\n"
        "• Type (Movie / Web Series / Episode)\n"
        "• Title → Sample → Trailer → Stream links\n"
        "• Quality size + download links\n"
        "• Optional Screenshots → Hashtags\n"
        "• Confirm (Rich Message)\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "*MODE 2 — Bulk paste*\n"
        "• `/bulk`\n"
        "• Poster photo (optional)\n"
        "• Poora caption *copy-paste*\n"
        "• Links auto *clickable* (blue)\n"
        "• Send to Me / Channel\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "*Channel*\n"
        "`/setchannel @Channel` — set\n"
        "`/getchannel` — current\n"
        "`/removechannel` — remove\n"
        "Bot ko channel pe *Admin* banao\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "*Admins* (owner only)\n"
        "`/addadmin <user_id>`\n"
        "`/removeadmin <user_id>`\n"
        "`/admins`\n\n"
        "`/cancel` — process band\n"
        "`/help` — yeh message"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MAIN_OWNER_ID:
        await update.message.reply_text("⛔ Sirf main owner hi admin add kar sakta hai.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        new_id = int(context.args[0])
        ADMINS.add(new_id)
        save_admins(ADMINS)
        await update.message.reply_text(
            f"✅ Admin add ho gaya: `{new_id}`", parse_mode=ParseMode.MARKDOWN
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID")


async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MAIN_OWNER_ID:
        await update.message.reply_text("⛔ Sirf main owner hi admin hata sakta hai.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        rem_id = int(context.args[0])
        if rem_id == MAIN_OWNER_ID:
            await update.message.reply_text("❌ Main owner ko nahi hata sakte.")
            return
        ADMINS.discard(rem_id)
        save_admins(ADMINS)
        await update.message.reply_text(
            f"✅ Admin hata diya: `{rem_id}`", parse_mode=ParseMode.MARKDOWN
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID")


async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = "👑 *Admins List:*\n\n"
    for aid in sorted(ADMINS):
        mark = " (Main Owner)" if aid == MAIN_OWNER_ID else ""
        text += f"`{aid}`{mark}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)



async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: /setchannel @channel or -100xxxx"""
    if update.effective_user.id != MAIN_OWNER_ID:
        await update.message.reply_text("⛔ Sirf main owner channel set kar sakta hai.")
        return
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "`/setchannel @YourChannel`\n"
            "ya\n"
            "`/setchannel -100xxxxxxxxxx`\n\n"
            "Bot ko channel mein *Admin* banao (Post messages on).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    raw = context.args[0].strip()
    # Accept @username or numeric id
    if raw.startswith("@"):
        channel_id = raw
    else:
        try:
            channel_id = int(raw)
        except ValueError:
            await update.message.reply_text("❌ Invalid. Use @username or numeric channel id.")
            return
    save_channel(channel_id)
    await update.message.reply_text(
        f"✅ Channel set: `{channel_id}`\n\n"
        "Bot ko is channel mein Admin banao.\n"
        "Confirm pe *Send to Channel* option aayega.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def get_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ch = load_channel()
    if ch:
        await update.message.reply_text(
            f"📢 Current channel: `{ch}`\n\n"
            "Change: `/setchannel @NewChannel`\n"
            "Remove: `/removechannel`",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            "📭 Channel set nahi hai.\n"
            "`/setchannel @YourChannel` se set karo.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MAIN_OWNER_ID:
        await update.message.reply_text("⛔ Sirf main owner.")
        return
    clear_channel()
    await update.message.reply_text("✅ Channel hata diya. Ab sirf private chat pe post hoga.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id:
        to_delete = context.user_data.get("to_delete", [])
        if update.callback_query:
            to_delete.append(update.callback_query.message.message_id)
        for msg_id in to_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
    reset_post(context)
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text("❌ Cancelled.")
        except Exception:
            pass
    else:
        await update.message.reply_text(
            "❌ Cancelled. Naya post ke liye photo bhejo ya /new"
        )
    return ConversationHandler.END


# ========== ENTRY POINTS ==========
async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return ConversationHandler.END

    context.user_data["to_delete"] = []
    track(context, update.message)
    post = get_user_data(context)
    post["poster"] = None
    post["screenshots"] = []

    keyboard = [
        [
            InlineKeyboardButton("🎬 Movie", callback_data="type_movie"),
            InlineKeyboardButton("📺 Web Series", callback_data="type_webseries"),
        ],
        [InlineKeyboardButton("🎞 Episode / Show", callback_data="type_episode")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    msg = await update.message.reply_text(
        "📝 Type select karo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    track(context, msg)
    return SELECT_TYPE


async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return ConversationHandler.END

    post = context.user_data.get("post")
    if post and post.get("title"):
        return await screenshot_photo(update, context)

    context.user_data["to_delete"] = []
    track(context, update.message)
    post = get_user_data(context)
    post["poster"] = update.message.photo[-1].file_id
    post["screenshots"] = []

    keyboard = [
        [
            InlineKeyboardButton("🎬 Movie", callback_data="type_movie"),
            InlineKeyboardButton("📺 Web Series", callback_data="type_webseries"),
        ],
        [InlineKeyboardButton("🎞 Episode / Show", callback_data="type_episode")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    msg = await update.message.reply_text(
        "✅ Poster mil gaya!\n\nType select karo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    track(context, msg)
    return SELECT_TYPE


async def type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        return await cancel(update, context)

    post = get_user_data(context)
    if query.data == "type_movie":
        post["type"] = "movie"
    elif query.data == "type_webseries":
        post["type"] = "webseries"
    else:
        post["type"] = "episode"

    if not post.get("poster"):
        keyboard = [
            [InlineKeyboardButton("⏭ Skip Poster URL", callback_data="skip_poster")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        await query.edit_message_text(
            "🖼 Poster Image URL bhejo (TMDB / any .jpg link)\n\nYa Skip karo:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return WAITING_POSTER_URL

    await query.edit_message_text("📝 Ab *Title* bhejo:", parse_mode=ParseMode.MARKDOWN)
    return WAITING_TITLE


async def poster_url_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    text = update.message.text.strip()

    if is_image_url(text):
        post["poster"] = text
        msg = await update.message.reply_text(
            "✅ Poster URL save.\n\n📝 Ab *Title* bhejo:", parse_mode=ParseMode.MARKDOWN
        )
    else:
        msg = await update.message.reply_text(
            "⚠️ Valid image URL nahi. Phir se bhejo ya Skip dabao."
        )
        track(context, msg)
        return WAITING_POSTER_URL

    track(context, msg)
    return WAITING_TITLE


async def skip_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    post["poster"] = None
    await query.edit_message_text("📝 Ab *Title* bhejo:", parse_mode=ParseMode.MARKDOWN)
    return WAITING_TITLE


async def title_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        track(context, update.message)
        post = get_user_data(context)
        post["title"] = update.message.text.strip()

        keyboard = [
            [InlineKeyboardButton("⏭ Skip Sample", callback_data="skip_sample")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        msg = await update.message.reply_text(
            "🔗 Sample Link bhejo (ya Skip):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        track(context, msg)
        return WAITING_SAMPLE
    except Exception as e:
        logger.error(f"title_received error: {e}")
        try:
            await update.message.reply_text("⚠️ Error. Dobara Title bhejo ya /cancel")
        except Exception:
            pass
        return WAITING_TITLE


async def sample_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    post["sample"] = update.message.text.strip()
    return await ask_trailer(update, context)


async def skip_sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    post["sample"] = None
    return await ask_trailer(update, context, from_callback=True)


async def ask_trailer(update, context, from_callback=False):
    keyboard = [
        [InlineKeyboardButton("⏭ Skip Trailer", callback_data="skip_trailer")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    text = "🎬 Trailer Link bhejo (optional):"
    if from_callback:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        msg = await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        track(context, msg)
    return WAITING_TRAILER


async def trailer_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    post["trailer"] = update.message.text.strip()
    return await ask_stream(update, context)


async def skip_trailer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    post["trailer"] = None
    return await ask_stream(update, context, from_callback=True)


async def ask_stream(update, context, from_callback=False):
    keyboard = [
        [InlineKeyboardButton("⏭ Skip Watch/Stream", callback_data="skip_stream")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    text = "▶️ Watch / Stream Link bhejo (optional):\nMultiple links add kar sakte ho."
    if from_callback:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        msg = await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        track(context, msg)
    return WAITING_STREAM


async def stream_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    post["streams"].append(update.message.text.strip())

    keyboard = [
        [InlineKeyboardButton("➕ Add Another Stream Link", callback_data="add_more_stream")],
        [InlineKeyboardButton("✅ Done with Streams", callback_data="streams_done")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    msg = await update.message.reply_text(
        f"✅ Stream Link {len(post['streams'])} add ho gaya.\n\nAur add karna hai?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    track(context, msg)
    return WAITING_MORE_STREAM


async def skip_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    post["streams"] = []
    return await after_stream(update, context, from_callback=True)


async def more_stream_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    post = get_user_data(context)

    if data == "cancel":
        return await cancel(update, context)
    if data == "add_more_stream":
        await query.edit_message_text("▶️ Next Stream / Watch Link bhejo:")
        return WAITING_STREAM
    if data == "streams_done":
        return await after_stream(update, context, from_callback=True)
    return WAITING_MORE_STREAM


async def after_stream(update, context, from_callback=False):
    post = get_user_data(context)

    if post["type"] == "episode":
        text = "📺 Season number bhejo (jaise 1 ya 01):"
        if from_callback:
            await update.callback_query.edit_message_text(text)
        else:
            msg = await update.message.reply_text(text)
            track(context, msg)
        return WAITING_SEASON

    if post["type"] == "webseries":
        text = "📺 Pehle Season ka number bhejo (jaise 1):"
        if from_callback:
            await update.callback_query.edit_message_text(text)
        else:
            msg = await update.message.reply_text(text)
            track(context, msg)
        return WAITING_SEASON_NUM

    text = "📥 Ab quality links add karo:"
    kb = make_quality_keyboard(post)
    if from_callback:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        msg = await update.message.reply_text(text, reply_markup=kb)
        track(context, msg)
    return QUALITY_MENU


async def season_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    post["season"] = update.message.text.strip()
    msg = await update.message.reply_text("🎞 Episode number bhejo:")
    track(context, msg)
    return WAITING_EPISODE


async def episode_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    post["episode"] = update.message.text.strip()
    msg = await update.message.reply_text(
        "📥 Ab quality links add karo:",
        reply_markup=make_quality_keyboard(post),
    )
    track(context, msg)
    return QUALITY_MENU


async def season_num_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    season_num = update.message.text.strip()

    if season_num not in post["seasons"]:
        post["seasons"][season_num] = {
            q: {"size": None, "links": []} for q in DEFAULT_QUALITIES
        }

    post["current_season"] = season_num

    msg = await update.message.reply_text(
        f"📥 *Season {season_num}* ke liye quality links add karo:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=make_quality_keyboard(post),
    )
    track(context, msg)
    return QUALITY_MENU


async def quality_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    post = get_user_data(context)

    if data == "cancel":
        return await cancel(update, context)

    if data == "finish":
        keyboard = [
            [InlineKeyboardButton("⏭ Skip Screenshots", callback_data="skip_screenshots")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        await query.edit_message_text(
            "🖼 Screenshots bhejo (optional)\n\n"
            "Jitne chaho utne photo upload kar sakte ho.\n"
            "Jab ho jaye to *Done* dabao.\n\n"
            "Final post mein yeh expandable + slideshow banenge.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return WAITING_SCREENSHOTS

    if data in ("season_done", "add_another_season"):
        await query.edit_message_text(
            "📺 Agle Season ka number bhejo (ya Finish All se khatam karo):"
        )
        return WAITING_SEASON_NUM

    if data == "add_new_quality":
        await query.edit_message_text(
            "➕ Naya Quality ka naam bhejo (jaise: 2160p 4K):"
        )
        return WAITING_NEW_QUALITY

    if data.startswith("q_"):
        q_name = data[2:]
        post["current_quality"] = q_name
        await query.edit_message_text(
            f"📦 *{q_name}* ke liye Size bhejo (ya `skip`):",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_SIZE

    return QUALITY_MENU


async def new_quality_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    new_q = update.message.text.strip()
    qualities = get_current_qualities(post)

    if new_q in qualities:
        msg = await update.message.reply_text("⚠️ Yeh quality pehle se hai.")
        track(context, msg)
        return WAITING_NEW_QUALITY

    qualities[new_q] = {"size": None, "links": []}
    msg = await update.message.reply_text(
        f"✅ `{new_q}` add ho gaya!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=make_quality_keyboard(post),
    )
    track(context, msg)
    return QUALITY_MENU


async def size_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    text = update.message.text.strip()
    q = post["current_quality"]
    qualities = get_current_qualities(post)

    if text.lower() != "skip":
        qualities[q]["size"] = text
    else:
        qualities[q]["size"] = None

    msg = await update.message.reply_text(
        f"🔗 *{q}* → Download Link 1 bhejo:",
        parse_mode=ParseMode.MARKDOWN,
    )
    track(context, msg)
    return WAITING_LINK1


async def link1_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    q = post["current_quality"]
    qualities = get_current_qualities(post)
    qualities[q]["links"] = [update.message.text.strip()]

    keyboard = [[InlineKeyboardButton("⏭ Skip Link 2", callback_data="skip_link2")]]
    msg = await update.message.reply_text(
        f"🔗 *{q}* → Download Link 2 (optional):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    track(context, msg)
    return WAITING_LINK2


async def link2_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    q = post["current_quality"]
    qualities = get_current_qualities(post)
    link = update.message.text.strip()
    if link:
        qualities[q]["links"].append(link)

    msg = await update.message.reply_text(
        f"✅ *{q}* update ho gaya!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=make_quality_keyboard(post),
    )
    track(context, msg)
    return QUALITY_MENU


async def skip_link2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    q = post["current_quality"]
    await query.edit_message_text(
        f"✅ *{q}* update ho gaya! (1 link)",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=make_quality_keyboard(post),
    )
    return QUALITY_MENU


# ========== SCREENSHOTS ==========
async def screenshot_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    file_id = update.message.photo[-1].file_id

    if file_id not in post["screenshots"]:
        post["screenshots"].append(file_id)

    keyboard = [
        [InlineKeyboardButton("✅ Done with Screenshots", callback_data="screenshots_done")],
        [InlineKeyboardButton("⏭ Skip / No more", callback_data="skip_screenshots")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    msg = await update.message.reply_text(
        f"✅ Screenshot {len(post['screenshots'])} add ho gaya.\n\n"
        "Aur bhejo ya *Done* dabao:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    track(context, msg)
    return WAITING_SCREENSHOTS


async def screenshots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    post = get_user_data(context)

    if data == "cancel":
        return await cancel(update, context)

    if data in ("screenshots_done", "skip_screenshots"):
        if data == "skip_screenshots":
            post["screenshots"] = []
        keyboard = [
            [InlineKeyboardButton("⏭ Skip Hashtags", callback_data="skip_hashtags")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        await query.edit_message_text(
            "#️⃣ Hashtags bhejo (ya Skip):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return WAITING_HASHTAGS

    return WAITING_SCREENSHOTS


async def hashtags_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    post["hashtags"] = update.message.text.strip()
    return await show_preview(update, context)


async def skip_hashtags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    post["hashtags"] = None
    return await show_preview(update, context, from_callback=True)


async def show_preview(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback: bool = False):
    post = get_user_data(context)
    # Safe: short posts = full caption; long (8 seasons etc.) = compact summary
    caption = build_preview_caption(post)

    poster = post.get("poster")
    screenshots = post.get("screenshots") or []
    extra = ""
    if screenshots:
        extra = f"\n\n📸 {len(screenshots)} screenshot(s) → expandable slideshow in final post"

    try:
        if poster:
            if from_callback:
                preview_msg = await update.callback_query.message.reply_photo(
                    photo=poster,
                    caption=caption + extra,
                    parse_mode=ParseMode.HTML,
                )
                target = update.callback_query.message
            else:
                preview_msg = await update.message.reply_photo(
                    photo=poster,
                    caption=caption + extra,
                    parse_mode=ParseMode.HTML,
                )
                target = update.message
        else:
            if from_callback:
                preview_msg = await update.callback_query.message.reply_text(
                    caption + extra,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                target = update.callback_query.message
            else:
                preview_msg = await update.message.reply_text(
                    caption + extra,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                target = update.message
    except Exception as e:
        logger.error(f"Preview error: {e}")
        plain = (
            f"Title: {post.get('title') or '-'}\n"
            f"(Preview failed — final post still works)\n{e}"
        )
        if from_callback:
            preview_msg = await update.callback_query.message.reply_text(plain)
            target = update.callback_query.message
        else:
            preview_msg = await update.message.reply_text(plain)
            target = update.message

    track(context, preview_msg)

    ch = load_channel()
    keyboard = []
    if ch:
        keyboard.append([
            InlineKeyboardButton("📢 Send to Channel", callback_data="confirm_channel"),
        ])
        keyboard.append([
            InlineKeyboardButton("✅ Send to Me Only", callback_data="confirm_yes"),
            InlineKeyboardButton("✏️ Edit Again", callback_data="edit_again"),
        ])
        hint = (
            "👆 Preview\n\n"
            f"📢 Channel set: `{ch}`\n"
            "• *Send to Channel* → channel pe post (forward pe channel name)\n"
            "• *Send to Me Only* → sirf yahan\n"
            "Final post Rich Message (expandable Screenshots)."
        )
    else:
        keyboard.append([
            InlineKeyboardButton("✅ Confirm & Send (Rich)", callback_data="confirm_yes"),
            InlineKeyboardButton("✏️ Edit Again", callback_data="edit_again"),
        ])
        hint = (
            "👆 Preview\n\n"
            "Confirm pe final post *Rich Message* mein jayega\n"
            "(expandable Screenshots + slideshow).\n\n"
            "💡 Channel pe post ke liye: `/setchannel @YourChannel`"
        )
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    confirm_msg = await target.reply_text(
        hint,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    track(context, confirm_msg)
    return CONFIRM_POST


async def confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)

    if query.data == "cancel":
        return await cancel(update, context)

    if query.data == "edit_again":
        await query.edit_message_text(
            "✏️ Edit mode – quality links:",
            reply_markup=make_quality_keyboard(post),
        )
        return QUALITY_MENU

    if query.data in ("confirm_yes", "confirm_channel"):
        chat_id = query.message.chat_id
        to_channel = query.data == "confirm_channel"
        channel_id = load_channel() if to_channel else None

        if to_channel and not channel_id:
            await query.edit_message_text(
                "⚠️ Channel set nahi hai.\n`/setchannel @YourChannel` se set karo."
            )
            return CONFIRM_POST

        dest_label = f"channel `{channel_id}`" if to_channel else "private chat"
        await query.edit_message_text(
            f"⏳ Final post bhej raha hoon ({dest_label})..."
        )

        target = channel_id if to_channel else chat_id
        ok = await send_final_post(context, chat_id, post, target_chat_id=target)

        # Cleanup intermediate messages in private
        to_delete = context.user_data.get("to_delete", [])
        to_delete.append(query.message.message_id)
        for msg_id in to_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

        reset_post(context)

        if ok:
            if to_channel:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ Post *channel* pe bhej diya!\n"
                        f"📢 `{channel_id}`\n\n"
                        "Ab channel se forward karo — tag mein channel name aayega.\n"
                        "Naya post: photo bhejo ya /new"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Post bhej diya!\nNaya post: photo bhejo ya /new",
                )
        return ConversationHandler.END

    return CONFIRM_POST


# ================== FLASK ==================
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "SKxPoster Bot is Alive! ✅", 200


@flask_app.route("/health")
def health():
    return "OK", 200


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, threaded=True, use_reloader=False)


# ================== BULK MODE ==================
def bulk_footer_html() -> str:
    """Har bulk post ke end mein auto add."""
    return "\n".join([
        "<hr/>",
        "<p><b>📥 HOW TO DOWNLOAD</b></p>",
        f'<p>🔗 <a href="{HOW_TO_DOWNLOAD_URL}"><b>HOW TO DOWNLOAD MOVIE • WEB SERIES • SHOW BY LINK</b></a></p>',
        "<hr/>",
        f'<p>⚖️ <a href="{DMCA_IMAGE_URL}"><b>DMCA &amp; CONTENT DISCLAIMER</b></a></p>',
        "<p>We do not host any files. Takedown → @SKxMOVIES_RequestBot</p>",
        "<p>🔔 <b>STAY CONNECTED • STAY UPDATED</b> 🚀</p>",
    ])


def bulk_text_to_html(text: str) -> str:
    """
    User sirf TITLE + seasons + links paste kare.
    Links auto clickable.
    Footer (How to Download, DMCA, Stay Connected) bot khud add karega.
    """
    if not text:
        return ""

    raw = text.strip()
    raw = raw.replace("DMCA & CONTENT", "DMCA &amp; CONTENT")

    # Agar user ne already footer paste kiya ho to double na ho
    lower = raw.lower()
    has_footer = (
        "how to download" in lower
        or "dmca" in lower
        or "stay connected" in lower
    )

    lines_out = []
    # Blue note once at top of links section if missing
    if "blue text" not in lower and "clickable" not in lower:
        # will inject after title when we see first season / quality
        inject_note = True
    else:
        inject_note = False

    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines_out.append("")
            continue

        # Whole line URL → clickable Download Link
        if _re_full_url.match(stripped):
            if inject_note:
                lines_out.append("<p><i>🔵 Blue text = Clickable Download Link</i></p>")
                inject_note = False
            url = stripped
            lines_out.append(f'🔗 <a href="{url}">Download Link</a>')
            continue

        if "<a href" in stripped.lower():
            if inject_note and ("season" in stripped.lower() or "quality" in stripped.lower() or "480" in stripped or "720" in stripped or "1080" in stripped):
                lines_out.append("<p><i>🔵 Blue text = Clickable Download Link</i></p>")
                inject_note = False
            lines_out.append(stripped)
            continue

        safe = esc(stripped)

        def _linkify(m):
            u = m.group(0).replace("&amp;", "&")
            return f'<a href="{u}">{m.group(0)}</a>'

        safe = re.sub(r"https?://[^\s<>\"']+", _linkify, safe)

        upper = stripped.upper()
        if "SEASON" in upper and len(stripped) < 50:
            if inject_note:
                lines_out.append("<p><i>🔵 Blue text = Clickable Download Link</i></p>")
                inject_note = False
            lines_out.append(f"<p><b>{safe}</b></p>")
        elif stripped.startswith(("📥", "📺", "⚖️", "🔔", "🎬")):
            lines_out.append(f"<p><b>{safe}</b></p>")
        elif stripped.startswith("🔹") or stripped.startswith("📦"):
            lines_out.append(f"<p>{safe}</p>")
        else:
            lines_out.append(f"<p>{safe}</p>")

    html_parts = []
    blank = 0
    for ln in lines_out:
        if ln == "":
            blank += 1
            if blank <= 1:
                html_parts.append("")
        else:
            blank = 0
            html_parts.append(ln)

    body = "\n".join(html_parts)
    if not has_footer:
        body = body + "\n" + bulk_footer_html()
    return body


_re_full_url = re.compile(r"^https?://[^\s<>\"']+$")


async def bulk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return ConversationHandler.END

    context.user_data["bulk"] = {"poster": None, "text": None}
    context.user_data["to_delete"] = []
    track(context, update.message)

    keyboard = [
        [InlineKeyboardButton("⏭ Skip Poster", callback_data="bulk_skip_poster")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    msg = await update.message.reply_text(
        "📦 *BULK MODE*\n\n"
        "1. Poster photo bhejo (ya Skip)\n"
        "2. Sirf *TITLE + seasons + links* paste karo\n"
        "   (How to Download / DMCA bot *khud* add karega)\n"
        "3. Confirm → final post\n\n"
        "Poster photo bhejo:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    track(context, msg)
    return BULK_POSTER


async def bulk_poster_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    bulk = context.user_data.setdefault("bulk", {})
    bulk["poster"] = update.message.photo[-1].file_id

    msg = await update.message.reply_text(
        "✅ Poster save.\n\n"
        "Ab *poora caption* copy-paste karke bhejo "
        "(TITLE, seasons, links — jo text ready hai):",
        parse_mode=ParseMode.MARKDOWN,
    )
    track(context, msg)
    return BULK_TEXT


async def bulk_skip_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bulk = context.user_data.setdefault("bulk", {})
    bulk["poster"] = None
    await query.edit_message_text(
        "⏭ Poster skip.\n\n"
        "Ab *poora caption* copy-paste karke bhejo:",
        parse_mode=ParseMode.MARKDOWN,
    )
    return BULK_TEXT


async def bulk_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    bulk = context.user_data.setdefault("bulk", {})
    text = (update.message.text or "").strip()
    if len(text) < 20:
        msg = await update.message.reply_text(
            "⚠️ Caption bahut chhota hai. Poora text paste karo."
        )
        track(context, msg)
        return BULK_TEXT

    bulk["text"] = text
    html = bulk_text_to_html(text)
    bulk["html"] = html

    # Short preview
    preview = text[:600] + ("…" if len(text) > 600 else "")
    poster = bulk.get("poster")

    try:
        if poster:
            pmsg = await update.message.reply_photo(
                photo=poster,
                caption=esc(preview)[:1000],
                parse_mode=ParseMode.HTML,
            )
        else:
            pmsg = await update.message.reply_text(
                preview[:3500],
                disable_web_page_preview=True,
            )
        track(context, pmsg)
    except Exception as e:
        logger.warning(f"bulk preview: {e}")
        pmsg = await update.message.reply_text(
            f"(Preview skip)\nChars: {len(text)}"
        )
        track(context, pmsg)

    ch = load_channel()
    keyboard = []
    if ch:
        keyboard.append([
            InlineKeyboardButton("📢 Send to Channel", callback_data="bulk_channel"),
        ])
    keyboard.append([
        InlineKeyboardButton("✅ Send to Me", callback_data="bulk_me"),
    ])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

    cmsg = await update.message.reply_text(
        f"✅ Caption mil gaya ({len(text)} chars).\n\n"
        "Final post bhejo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    track(context, cmsg)
    return BULK_CONFIRM


async def bulk_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        return await cancel(update, context)

    bulk = context.user_data.get("bulk") or {}
    html = bulk.get("html") or bulk_text_to_html(bulk.get("text") or "")
    poster = bulk.get("poster")
    chat_id = query.message.chat_id

    to_channel = query.data == "bulk_channel"
    channel_id = load_channel() if to_channel else None
    if to_channel and not channel_id:
        await query.edit_message_text("⚠️ Channel set nahi. `/setchannel @Channel`")
        return BULK_CONFIRM

    dest = channel_id if to_channel else chat_id
    await query.edit_message_text("⏳ Bulk post bhej raha hoon...")

    media = []
    if poster:
        media.append({"id": "poster", "media": {"type": "photo", "media": poster}})
        final_html = f'<img src="tg://photo?id=poster"/>\n{html}'
    else:
        final_html = html

    token = context.bot.token
    ok = False
    try:
        await send_rich_message(token, dest, final_html, media)
        ok = True
    except Exception as e:
        logger.warning(f"Bulk rich failed: {e}")
        # Classic fallback
        try:
            cap = (bulk.get("text") or "")[:1000]
            if poster:
                await context.bot.send_photo(
                    chat_id=dest,
                    photo=poster,
                    caption=cap,
                )
            else:
                await context.bot.send_message(chat_id=dest, text=cap)
            ok = True
        except Exception as e2:
            await context.bot.send_message(
                chat_id=chat_id, text=f"⚠️ Error: {e2}"
            )

    # cleanup
    to_delete = context.user_data.get("to_delete", [])
    to_delete.append(query.message.message_id)
    for mid in to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

    context.user_data.pop("bulk", None)
    context.user_data.pop("to_delete", None)

    if ok:
        where = f"channel `{channel_id}`" if to_channel else "yahan"
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Bulk post bhej diya ({where})!\n/bulk ya photo se naya.",
            parse_mode=ParseMode.MARKDOWN,
        )
    return ConversationHandler.END



def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please set BOT_TOKEN environment variable!")
        return

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask keep-alive started on port {PORT}")

    async def post_init(application: Application):
        await application.bot.set_my_commands([
            BotCommand("start", "Start / welcome"),
            BotCommand("new", "Step-by-step naya post"),
            BotCommand("bulk", "Bulk: poster + caption paste"),
            BotCommand("cancel", "Current process cancel"),
            BotCommand("setchannel", "Channel set (@name)"),
            BotCommand("getchannel", "Current channel dekho"),
            BotCommand("removechannel", "Channel hatao"),
            BotCommand("admins", "Admin list"),
            BotCommand("help", "Full help"),
        ])
        logger.info("Bot commands menu set")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Exception while handling update: {context.error}")
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Kuch technical error aa gaya. /cancel karke dobara try karo."
                )
            except Exception:
                pass

    app.add_error_handler(error_handler)

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, photo_received),
            CommandHandler("new", new_command),
        ],
        states={
            SELECT_TYPE: [CallbackQueryHandler(type_selected)],
            WAITING_POSTER_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, poster_url_received),
                CallbackQueryHandler(skip_poster, pattern="^skip_poster$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            WAITING_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, title_received)
            ],
            WAITING_SAMPLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sample_received),
                CallbackQueryHandler(skip_sample, pattern="^skip_sample$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            WAITING_TRAILER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trailer_received),
                CallbackQueryHandler(skip_trailer, pattern="^skip_trailer$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            WAITING_STREAM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, stream_received),
                CallbackQueryHandler(skip_stream, pattern="^skip_stream$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            WAITING_MORE_STREAM: [CallbackQueryHandler(more_stream_handler)],
            WAITING_SEASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, season_received)
            ],
            WAITING_EPISODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, episode_received)
            ],
            WAITING_SEASON_NUM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, season_num_received)
            ],
            QUALITY_MENU: [CallbackQueryHandler(quality_menu_handler)],
            WAITING_SIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, size_received)
            ],
            WAITING_LINK1: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link1_received)
            ],
            WAITING_LINK2: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link2_received),
                CallbackQueryHandler(skip_link2, pattern="^skip_link2$"),
            ],
            WAITING_NEW_QUALITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_quality_received)
            ],
            WAITING_SCREENSHOTS: [
                MessageHandler(filters.PHOTO, screenshot_photo),
                CallbackQueryHandler(screenshots_callback),
            ],
            WAITING_HASHTAGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, hashtags_received),
                CallbackQueryHandler(skip_hashtags, pattern="^skip_hashtags$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            CONFIRM_POST: [CallbackQueryHandler(confirm_handler)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$"),
        ],
        allow_reentry=False,
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("admins", list_admins))
    app.add_handler(CommandHandler("setchannel", set_channel))
    app.add_handler(CommandHandler("getchannel", get_channel))
    app.add_handler(CommandHandler("removechannel", remove_channel))

    bulk_handler = ConversationHandler(
        entry_points=[CommandHandler("bulk", bulk_start)],
        states={
            BULK_POSTER: [
                MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, bulk_poster_photo),
                CallbackQueryHandler(bulk_skip_poster, pattern="^bulk_skip_poster$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            BULK_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_text_received),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            BULK_CONFIRM: [
                CallbackQueryHandler(bulk_confirm, pattern="^bulk_(me|channel)$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$"),
        ],
        allow_reentry=False,
        per_message=False,
    )
    app.add_handler(bulk_handler)
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("cancel", cancel))

    print("✅ SKxPoster Bot (Rich Messages) starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
