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

# Default qualities
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
    WAITING_TITLE,
    WAITING_SAMPLE,
    WAITING_SEASON,
    WAITING_EPISODE,
    QUALITY_MENU,
    WAITING_SIZE,
    WAITING_LINK1,
    WAITING_LINK2,
    WAITING_NEW_QUALITY,
    WAITING_HASHTAGS,
    CONFIRM_POST,
) = range(12)

# Logging
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
ADMINS.add(MAIN_OWNER_ID)  # always keep main owner


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS or user_id == MAIN_OWNER_ID


# ================== HELPERS ==================
def get_user_data(context: ContextTypes.DEFAULT_TYPE):
    if "post" not in context.user_data:
        context.user_data["post"] = {
            "photo_file_id": None,
            "type": None,  # movie / webseries / episode
            "title": None,
            "sample": None,
            "season": None,
            "episode": None,
            "qualities": {q: {"size": None, "links": []} for q in DEFAULT_QUALITIES},
            "current_quality": None,
            "hashtags": None,
        }
    return context.user_data["post"]


def reset_post(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("post", None)


def make_quality_keyboard(post_data):
    buttons = []
    row = []
    for i, q in enumerate(post_data["qualities"].keys()):
        status = "✅" if post_data["qualities"][q]["links"] else "⬜"
        row.append(InlineKeyboardButton(f"{status} {q}", callback_data=f"q_{q}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("➕ Add New Quality", callback_data="add_new_quality"),
    ])
    buttons.append([
        InlineKeyboardButton("✅ Finish & Continue", callback_data="finish"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(buttons)


def generate_caption(post):
    lines = []

    # Title
    lines.append("🎬 <b>𝗧𝗜𝗧𝗟𝗘</b>")
    lines.append(f'"{post["title"]}"')
    lines.append("")

    # Season / Episode (only for episode)
    if post["type"] == "episode" and post.get("season") and post.get("episode"):
        lines.append(f"📺 <b>Season {post['season']} • Episode {post['episode']}</b>")
        lines.append("")

    # Sample (only if present)
    if post.get("sample"):
        lines.append("🎞️ <b>𝗦𝗔𝗠𝗣𝗟𝗘</b>")
        lines.append(f'🔗 <a href="{post["sample"]}">Sample Link</a>')
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("📥 <b>𝗔𝗟𝗟 𝗤𝗨𝗔𝗟𝗜𝗧𝗬 𝗟𝗜𝗡𝗞𝗦</b>")
    lines.append("")

    for q_name, q_data in post["qualities"].items():
        lines.append(f"🔹 <b>{q_name}</b>")
        if q_data["links"]:
            size = q_data["size"] if q_data["size"] else "—"
            lines.append(f'📦 Size: "{size}"')
            for idx, link in enumerate(q_data["links"], 1):
                lines.append(f'🔗 <a href="{link}">Download Link {idx}</a>')
        else:
            lines.append("🔜 Added Soon")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("📌 <b>𝗟𝗜𝗡𝗞 𝗦𝗧𝗔𝗧𝗨𝗦</b>")
    lines.append("")
    lines.append("🔵 Blue Text → Link Added & Ready")
    lines.append("⚫ Black Text → 🔜 Added Soon")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("🌐 <b>𝗢𝗨𝗥 𝗢𝗧𝗛𝗘𝗥 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b>")
    lines.append("")
    lines.append("🎥 Movies | Web Series | Shows")
    lines.append("👉 @MoviesWebSeries_08")
    lines.append("")
    lines.append("🔗 𝐓𝐇𝐄 𝐒𝐊𝟎𝟖")
    lines.append("👉 @The_Sk08")
    lines.append("")
    lines.append("👑 SKxMOVIES")
    lines.append("👉 @SKxMOVIES")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("🔔 <b>𝗦𝗧𝗔𝗬 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 • 𝗦𝗧𝗔𝗬 𝗨𝗣𝗗𝗔𝗧𝗘𝗗</b> 🚀")

    # Hashtags at the very end (if provided)
    if post.get("hashtags"):
        lines.append("")
        lines.append(post["hashtags"])

    return "\n".join(lines)


# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Access Denied. This bot is private.")
        return

    await update.message.reply_text(
        f"👋 Welcome *{user.first_name}*!\n\n"
        "Yeh bot sirf aapke liye hai.\n\n"
        "📌 *Kaise use karein:*\n"
        "1. Poster/Image bhejo\n"
        "2. Type select karo\n"
        "3. Title + details daalo\n"
        "4. Quality links add karo\n"
        "5. Hashtags (optional)\n"
        "6. Finish pe final post mil jayega\n\n"
        "Commands:\n"
        "/cancel - Beech mein cancel\n"
        "/addadmin <user_id> - Naya admin add (sirf owner)\n"
        "/removeadmin <user_id>\n"
        "/admins - Admin list\n"
        "/help - Help",
        parse_mode=ParseMode.MARKDOWN,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🛠 *SKxPoster Bot Help*\n\n"
        "1. Koi bhi poster bhejo\n"
        "2. Movie / Web Series / Episode select karo\n"
        "3. Title bhejo\n"
        "4. Sample link (optional)\n"
        "5. Quality pe click karke Size + Links daalo\n"
        "6. Hashtags (optional)\n"
        "7. Finish & Preview → Confirm\n\n"
        "Admin commands (Owner only):\n"
        "`/addadmin 123456789`\n"
        "`/removeadmin 123456789`\n"
        "`/admins`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != MAIN_OWNER_ID:
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
    user = update.effective_user
    if user.id != MAIN_OWNER_ID:
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
    reset_post(context)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Cancelled.")
    else:
        await update.message.reply_text("❌ Cancelled. Naya post shuru karne ke liye photo bhejo.")
    return ConversationHandler.END


# ========== PHOTO RECEIVED ==========
async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return ConversationHandler.END

    post = get_user_data(context)
    post["photo_file_id"] = update.message.photo[-1].file_id

    keyboard = [
        [
            InlineKeyboardButton("🎬 Movie", callback_data="type_movie"),
            InlineKeyboardButton("📺 Web Series", callback_data="type_webseries"),
        ],
        [
            InlineKeyboardButton("🎞 Episode / Show", callback_data="type_episode"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    await update.message.reply_text(
        "✅ Poster mil gaya!\n\nAb type select karo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
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

    await query.edit_message_text("📝 Ab *Title* bhejo (Movie / Series ka naam):", parse_mode=ParseMode.MARKDOWN)
    return WAITING_TITLE


async def title_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_user_data(context)
    post["title"] = update.message.text.strip()

    keyboard = [
        [InlineKeyboardButton("⏭ Skip Sample Link", callback_data="skip_sample")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    await update.message.reply_text(
        "🔗 Sample Link bhejo (ya Skip karo):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAITING_SAMPLE


async def sample_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_user_data(context)
    post["sample"] = update.message.text.strip()

    if post["type"] == "episode":
        await update.message.reply_text("📺 Season number bhejo (jaise 1 ya 01):")
        return WAITING_SEASON
    else:
        await update.message.reply_text(
            "📥 Ab quality links add karo:",
            reply_markup=make_quality_keyboard(post),
        )
        return QUALITY_MENU


async def skip_sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    post["sample"] = None

    if post["type"] == "episode":
        await query.edit_message_text("📺 Season number bhejo (jaise 1 ya 01):")
        return WAITING_SEASON
    else:
        await query.edit_message_text(
            "📥 Ab quality links add karo:",
            reply_markup=make_quality_keyboard(post),
        )
        return QUALITY_MENU


async def season_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_user_data(context)
    post["season"] = update.message.text.strip()
    await update.message.reply_text("🎞 Episode number bhejo (jaise 5 ya 05):")
    return WAITING_EPISODE


async def episode_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_user_data(context)
    post["episode"] = update.message.text.strip()
    await update.message.reply_text(
        "📥 Ab quality links add karo:",
        reply_markup=make_quality_keyboard(post),
    )
    return QUALITY_MENU


# ========== QUALITY MENU ==========
async def quality_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    post = get_user_data(context)

    if data == "cancel":
        return await cancel(update, context)

    if data == "finish":
        # Go to hashtags step
        keyboard = [
            [InlineKeyboardButton("⏭ Skip Hashtags", callback_data="skip_hashtags")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        await query.edit_message_text(
            "#️⃣ Hashtags bhejo (jaise: #Movie #WebSeries #SKxMOVIES)\n\n"
            "Ya Skip karo agar nahi chahiye:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return WAITING_HASHTAGS

    if data == "add_new_quality":
        await query.edit_message_text("➕ Naya Quality ka naam bhejo (jaise: 2160p 4K):")
        return WAITING_NEW_QUALITY

    if data.startswith("q_"):
        q_name = data[2:]
        post["current_quality"] = q_name
        await query.edit_message_text(
            f"📦 *{q_name}* ke liye Size bhejo (jaise: 1.4 GB)\n\n"
            "Agar size nahi dena to `skip` likh do.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_SIZE

    return QUALITY_MENU


async def new_quality_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_user_data(context)
    new_q = update.message.text.strip()
    if new_q in post["qualities"]:
        await update.message.reply_text("⚠️ Yeh quality pehle se hai. Koi aur naam do.")
        return WAITING_NEW_QUALITY

    post["qualities"][new_q] = {"size": None, "links": []}
    await update.message.reply_text(
        f"✅ `{new_q}` add ho gaya!\n\nAb links add karo:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=make_quality_keyboard(post),
    )
    return QUALITY_MENU


async def size_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_user_data(context)
    text = update.message.text.strip()
    q = post["current_quality"]

    if text.lower() != "skip":
        post["qualities"][q]["size"] = text
    else:
        post["qualities"][q]["size"] = None

    await update.message.reply_text(
        f"🔗 *{q}* ke liye Download Link 1 bhejo:",
        parse_mode=ParseMode.MARKDOWN,
    )
    return WAITING_LINK1


async def link1_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_user_data(context)
    q = post["current_quality"]
    link = update.message.text.strip()
    post["qualities"][q]["links"] = [link]  # reset + add first

    keyboard = [
        [InlineKeyboardButton("⏭ Skip Link 2", callback_data="skip_link2")],
    ]
    await update.message.reply_text(
        f"🔗 *{q}* ke liye Download Link 2 bhejo (optional):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAITING_LINK2


async def link2_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_user_data(context)
    q = post["current_quality"]
    link = update.message.text.strip()
    if link:
        post["qualities"][q]["links"].append(link)

    await update.message.reply_text(
        f"✅ *{q}* update ho gaya!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=make_quality_keyboard(post),
    )
    return QUALITY_MENU


async def skip_link2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)
    q = post["current_quality"]

    await query.edit_message_text(
        f"✅ *{q}* update ho gaya! (sirf 1 link)",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=make_quality_keyboard(post),
    )
    return QUALITY_MENU


# ========== HASHTAGS ==========
async def hashtags_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Send preview photo
    if from_callback:
        await update.callback_query.message.reply_photo(
            photo=post["photo_file_id"],
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        target = update.callback_query.message
    else:
        await update.message.reply_photo(
            photo=post["photo_file_id"],
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        target = update.message

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm & Send to Me", callback_data="confirm_yes"),
            InlineKeyboardButton("✏️ Edit Again", callback_data="edit_again"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    await target.reply_text(
        "👆 Yeh raha Preview.\n\nConfirm karein?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CONFIRM_POST


async def confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post = get_user_data(context)

    if query.data == "cancel":
        return await cancel(update, context)

    if query.data == "edit_again":
        await query.edit_message_text(
            "✏️ Edit mode:\nQuality links add/edit karo:",
            reply_markup=make_quality_keyboard(post),
        )
        return QUALITY_MENU

    if query.data == "confirm_yes":
        caption = generate_caption(post)
        # Final send to user
        await query.message.reply_photo(
            photo=post["photo_file_id"],
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        await query.message.reply_text(
            "✅ Final post aapko bhej diya gaya!\n\n"
            "Aap isko copy/forward kar sakte ho.\n\n"
            "Naya post banane ke liye dubara photo bhejo."
        )
        reset_post(context)
        return ConversationHandler.END

    return CONFIRM_POST


# ================== FLASK KEEP-ALIVE ==================
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "SKxPoster Bot is Alive! ✅", 200


@flask_app.route("/health")
def health():
    return "OK", 200


def run_flask():
    # Use threaded=True and disable reloader for stability on Render
    flask_app.run(host="0.0.0.0", port=PORT, threaded=True, use_reloader=False)


# ================== MAIN ==================
def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please set BOT_TOKEN environment variable!")
        return

    # Critical fix for Render + Python 3.10+/3.12+ event loop issue
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Start Flask in background for UptimeRobot
    Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask keep-alive started on port {PORT}")

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, photo_received),
        ],
        states={
            SELECT_TYPE: [
                CallbackQueryHandler(type_selected),
            ],
            WAITING_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, title_received),
            ],
            WAITING_SAMPLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sample_received),
                CallbackQueryHandler(skip_sample, pattern="^skip_sample$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            WAITING_SEASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, season_received),
            ],
            WAITING_EPISODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, episode_received),
            ],
            QUALITY_MENU: [
                CallbackQueryHandler(quality_menu_handler),
            ],
            WAITING_SIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, size_received),
            ],
            WAITING_LINK1: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link1_received),
            ],
            WAITING_LINK2: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link2_received),
                CallbackQueryHandler(skip_link2, pattern="^skip_link2$"),
            ],
            WAITING_NEW_QUALITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_quality_received),
            ],
            WAITING_HASHTAGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, hashtags_received),
                CallbackQueryHandler(skip_hashtags, pattern="^skip_hashtags$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            CONFIRM_POST: [
                CallbackQueryHandler(confirm_handler),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$"),
        ],
        allow_reentry=True,
        per_message=False,  # silence the warning
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("admins", list_admins))
    app.add_handler(conv_handler)

    # Also allow cancel anytime
    app.add_handler(CommandHandler("cancel", cancel))

    print("✅ SKxPoster Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
