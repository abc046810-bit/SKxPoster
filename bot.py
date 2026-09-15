import os
import json
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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

DEFAULT_QUALITIES = [
    "480p",
    "720p HEVC",
    "720p x264",
    "1080p HEVC",
    "1080p x264",
    "HQ-Rip 1080p",
    "HQ 1080p",
]

# Conversation states
(
    SELECT_TYPE,
    WAITING_POSTER_URL,
    WAITING_TITLE,
    WAITING_SAMPLE,
    WAITING_TRAILER,
    WAITING_STREAM,
    WAITING_SEASON,
    WAITING_EPISODE,
    WAITING_SEASON_NUM,
    QUALITY_MENU,
    WAITING_SIZE,
    WAITING_LINK1,
    WAITING_LINK2,
    WAITING_NEW_QUALITY,
    WAITING_HASHTAGS,
    CONFIRM_POST,
) = range(16)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ================== ADMIN SYSTEM ==================
ADMINS_FILE = "admins.json"


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
            "poster": None,          # file_id OR http image URL
            "type": None,
            "title": None,
            "sample": None,
            "trailer": None,         # Trailer link (separate)
            "stream": None,          # Watch / Stream full link (separate)
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


def generate_caption(post):
    lines = []

    lines.append("🎬 <b>𝗧𝗜𝗧𝗟𝗘</b>")
    lines.append(f'"{post["title"]}"')
    lines.append("")

    if post["type"] == "episode" and post.get("season") and post.get("episode"):
        lines.append(f"📺 <b>Season {post['season']} • Episode {post['episode']}</b>")
        lines.append("")

    if post.get("sample"):
        lines.append("🎞️ <b>𝗦𝗔𝗠𝗣𝗟𝗘</b>")
        lines.append(f'🔗 <a href="{post["sample"]}">Sample Link</a>')
        lines.append("")

    # Trailer (separate)
    if post.get("trailer"):
        lines.append("🎬 <b>𝗧𝗥𝗔𝗜𝗟𝗘𝗥</b>")
        lines.append(f'🔗 <a href="{post["trailer"]}">Watch Trailer</a>')
        lines.append("")

    # Watch / Stream (separate)
    if post.get("stream"):
        lines.append("▶️ <b>𝗪𝗔𝗧𝗖𝗛 / 𝗦𝗧𝗥𝗘𝗔𝗠</b>")
        lines.append(f'🔗 <a href="{post["stream"]}">Watch Online</a>')
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("📥 <b>𝗔𝗟𝗟 𝗤𝗨𝗔𝗟𝗜𝗧𝗬 𝗟𝗜𝗡𝗞𝗦</b>")
    lines.append("")

    if post["type"] == "webseries" and post.get("seasons"):
        for season_num in sorted(post["seasons"].keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            qualities = post["seasons"][season_num]
            has_any = any(q["links"] for q in qualities.values())
            if not has_any:
                continue
            lines.append(f"📺 <b>𝗦𝗘𝗔𝗦𝗢𝗡 {season_num}</b>")
            lines.append("")
            for q_name, q_data in qualities.items():
                if q_data["links"]:
                    lines.append(f"🔹 <b>{q_name}</b>")
                    size = q_data["size"] if q_data["size"] else "—"
                    lines.append(f'📦 Size: "{size}"')
                    for idx, link in enumerate(q_data["links"], 1):
                        lines.append(f'🔗 <a href="{link}">Download Link {idx}</a>')
                    lines.append("")
            lines.append("")
    else:
        for q_name, q_data in post["qualities"].items():
            if q_data["links"]:
                lines.append(f"🔹 <b>{q_name}</b>")
                size = q_data["size"] if q_data["size"] else "—"
                lines.append(f'📦 Size: "{size}"')
                for idx, link in enumerate(q_data["links"], 1):
                    lines.append(f'🔗 <a href="{link}">Download Link {idx}</a>')
                lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("🌐 <b>𝗢𝗨𝗥 𝗢𝗧𝗛𝗘𝗥 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b>")
    lines.append("")
    lines.append("🎥 Movies | Web Series | Shows")
    lines.append("👉 @MoviesWebSeries_08")
    lines.append("")
    lines.append("🔗 MOVIE LINKS")
    lines.append("👉 @Movielink_08")
    lines.append("")
    lines.append("🤖 𝐑𝐄𝐐𝐔𝐄𝐒𝐓 𝐁𝐎𝐓")
    lines.append("👉 @SKxMOVIES_RequestBot")
    lines.append("")
    lines.append("💭 𝐎𝐏𝐄𝐍 𝐂𝐇𝐀𝐓")
    lines.append("👉 @New_Movie_Chat")
    lines.append("")
    lines.append("👑 SKxMOVIES")
    lines.append("👉 @SKxMOVIES")
    lines.append("")
    lines.append("📢 THE SK08")
    lines.append("👉 @The_Sk08")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("🔔 <b>𝗦𝗧𝗔𝗬 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 • 𝗦𝗧𝗔𝗬 𝗨𝗣𝗗𝗔𝗧𝗘𝗗</b> 🚀")

    if post.get("hashtags"):
        lines.append("")
        lines.append(post["hashtags"])

    return "\n".join(lines)


def is_image_url(text: str) -> bool:
    text = text.strip().lower()
    if not text.startswith(("http://", "https://")):
        return False
    return any(ext in text for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]) or "image.tmdb.org" in text or "tmdb.org" in text


# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Access Denied. This bot is private.")
        return

    await update.message.reply_text(
        f"👋 Welcome *{user.first_name}*!\n\n"
        "📌 *Kaise use karein:*\n"
        "• Photo bhejo *ya* `/new` *ya* Poster URL\n"
        "• Type → Title → Sample → Trailer → Watch/Stream → Qualities\n"
        "• Web Series: multiple seasons support\n\n"
        "Commands:\n"
        "/new - Bina photo ke start\n"
        "/cancel\n"
        "/addadmin <id>\n"
        "/removeadmin <id>\n"
        "/admins\n"
        "/help",
        parse_mode=ParseMode.MARKDOWN,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🛠 *SKxPoster Help*\n\n"
        "1. Photo / Poster URL / `/new`\n"
        "2. Type select\n"
        "3. Title → Sample (opt) → Trailer (opt) → Watch/Stream (opt)\n"
        "4. Web Series: Season by Season\n"
        "5. Finish → Hashtags (opt) → Confirm\n\n"
        "Sirf linked qualities final post mein aayengi.",
        parse_mode=ParseMode.MARKDOWN,
    )


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
        await update.message.reply_text(f"✅ Admin add ho gaya: `{new_id}`", parse_mode=ParseMode.MARKDOWN)
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
        await update.message.reply_text(f"✅ Admin hata diya: `{rem_id}`", parse_mode=ParseMode.MARKDOWN)
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
        await update.message.reply_text("❌ Cancelled. Naya post ke liye photo / URL bhejo ya /new")
    return ConversationHandler.END


# ========== ENTRY: /new ==========
async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return ConversationHandler.END

    context.user_data["to_delete"] = []
    track(context, update.message)

    post = get_user_data(context)
    post["poster"] = None

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


# ========== ENTRY: Photo upload ==========
async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return ConversationHandler.END

    context.user_data["to_delete"] = []
    track(context, update.message)

    post = get_user_data(context)
    post["poster"] = update.message.photo[-1].file_id

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


# ========== ENTRY: Image URL as first message ==========
async def possible_poster_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    if not is_image_url(text):
        return ConversationHandler.END

    context.user_data["to_delete"] = []
    track(context, update.message)

    post = get_user_data(context)
    post["poster"] = text

    keyboard = [
        [
            InlineKeyboardButton("🎬 Movie", callback_data="type_movie"),
            InlineKeyboardButton("📺 Web Series", callback_data="type_webseries"),
        ],
        [InlineKeyboardButton("🎞 Episode / Show", callback_data="type_episode")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    msg = await update.message.reply_text(
        "✅ Poster URL mil gaya!\n\nType select karo:",
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
            "🖼 Poster Image URL bhejo (TMDB / any .jpg link)\n\n"
            "Example:\n`https://image.tmdb.org/t/p/w500/xxxx.jpg`\n\n"
            "Ya Skip karo:",
            parse_mode=ParseMode.MARKDOWN,
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
        msg = await update.message.reply_text("✅ Poster URL save ho gaya.\n\n📝 Ab *Title* bhejo:", parse_mode=ParseMode.MARKDOWN)
    else:
        msg = await update.message.reply_text(
            "⚠️ Valid image URL nahi lag raha.\n"
            "Phir se .jpg/.png link bhejo ya Skip button dabao."
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
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
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
    text = "▶️ Watch / Stream Link bhejo (full movie/series, optional):"
    if from_callback:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        track(context, msg)
    return WAITING_STREAM


async def stream_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(context, update.message)
    post = get_user_data(context)
    post["stream"] = update.message.text.strip()
    return await after_stream(update, context)


async def skip_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    post["stream"] = None
    return await after_stream(update, context, from_callback=True)


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
        post["seasons"][season_num] = {q: {"size": None, "links": []} for q in DEFAULT_QUALITIES}

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
            [InlineKeyboardButton("⏭ Skip Hashtags", callback_data="skip_hashtags")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        await query.edit_message_text(
            "#️⃣ Hashtags bhejo (ya Skip):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return WAITING_HASHTAGS

    if data == "season_done" or data == "add_another_season":
        await query.edit_message_text("📺 Agle Season ka number bhejo (ya Finish All se khatam karo):")
        return WAITING_SEASON_NUM

    if data == "add_new_quality":
        await query.edit_message_text("➕ Naya Quality ka naam bhejo (jaise: 2160p 4K):")
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
    link = update.message.text.strip()
    qualities[q]["links"] = [link]

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
    caption = generate_caption(post)
    poster = post.get("poster")

    if poster:
        if from_callback:
            preview_msg = await update.callback_query.message.reply_photo(
                photo=poster,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            target = update.callback_query.message
        else:
            preview_msg = await update.message.reply_photo(
                photo=poster,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            target = update.message
    else:
        if from_callback:
            preview_msg = await update.callback_query.message.reply_text(
                caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            target = update.callback_query.message
        else:
            preview_msg = await update.message.reply_text(
                caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            target = update.message

    track(context, preview_msg)

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm & Send", callback_data="confirm_yes"),
            InlineKeyboardButton("✏️ Edit Again", callback_data="edit_again"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    confirm_msg = await target.reply_text(
        "👆 Preview\n\nConfirm karein?",
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

    if query.data == "confirm_yes":
        caption = generate_caption(post)
        chat_id = query.message.chat_id
        poster = post.get("poster")

        if poster:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=poster,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

        to_delete = context.user_data.get("to_delete", [])
        to_delete.append(query.message.message_id)
        for msg_id in to_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

        reset_post(context)
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

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, photo_received),
            CommandHandler("new", new_command),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                possible_poster_url,
            ),
        ],
        states={
            SELECT_TYPE: [CallbackQueryHandler(type_selected)],
            WAITING_POSTER_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, poster_url_received),
                CallbackQueryHandler(skip_poster, pattern="^skip_poster$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            WAITING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_received)],
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
            WAITING_SEASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, season_received)],
            WAITING_EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, episode_received)],
            WAITING_SEASON_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, season_num_received)],
            QUALITY_MENU: [CallbackQueryHandler(quality_menu_handler)],
            WAITING_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, size_received)],
            WAITING_LINK1: [MessageHandler(filters.TEXT & ~filters.COMMAND, link1_received)],
            WAITING_LINK2: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link2_received),
                CallbackQueryHandler(skip_link2, pattern="^skip_link2$"),
            ],
            WAITING_NEW_QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_quality_received)],
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
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("admins", list_admins))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("cancel", cancel))

    print("✅ SKxPoster Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
