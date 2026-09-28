# SKxPoster Bot (@SKxPosterBot)

Private Telegram bot for **Movie / Web Series / Show** posts.

Uses **Telegram Rich Messages** (expandable Screenshots + slideshow) and can post **directly to your channel** (so forward tag shows channel name, not bot).

---

## Features

- Owner-only + multi-admin system
- Movie / Web Series (multi-season) / Episode flow
- Optional: Sample, Trailer, multiple Watch/Stream links
- Quality links with size (only qualities that have links appear)
- Optional Screenshots → **expandable section + swipe slideshow**
- How to Download (clickable)
- DMCA & Content Disclaimer (clickable image)
- Professional styled caption (Rich Message, ~32k char limit)
- **Direct post to Channel** (forward pe channel name, bot name nahi)
- Auto-delete intermediate messages in private chat
- Render free Web Service + UptimeRobot keep-alive ready
- Fallback to classic album if Rich Message fails

---

## Deploy on Render (Free)

1. Push this folder to GitHub
2. Render → **New → Web Service**
3. Environment variables:
   - `BOT_TOKEN` = token from @BotFather
   - `PORT` = `8080` (optional)
4. Start command: `python bot.py`
5. UptimeRobot → HTTP monitor on your Render URL (every 5 min)

---

## Channel setup (recommended)

1. Apna channel banao (public ya private)
2. Bot ko channel mein **Admin** banao → permission: **Post Messages**
3. Bot mein command:
   ```
   /setchannel @YourChannel
   ```
   ya numeric id:
   ```
   /setchannel -100xxxxxxxxxx
   ```
4. Confirm pe **📢 Send to Channel** dabao
5. Channel se forward karo → tag mein **channel name** aayega (bot name nahi)

Commands:
- `/setchannel @Channel` — set
- `/getchannel` — current channel dekho
- `/removechannel` — hatao (phir sirf private pe post)

---

## How to use

1. Poster photo bhejo **ya** `/new`
2. Type select (Movie / Web Series / Episode)
3. Title → Sample (optional) → Trailer (optional) → Stream links (optional, multiple)
4. Quality size + download links
5. Screenshots upload (optional) → **Done**
6. Hashtags (optional)
7. Preview →
   - **Send to Channel** (agar set hai)
   - **Send to Me Only**

Final post = Rich Message:
- Structured TITLE / SAMPLE / TRAILER / STREAM / QUALITY
- **📸 SCREENSHOTS — Tap to open & swipe**
- How to Download + DMCA + Stay Connected

---

## Commands

| Command | Who | Description |
|---------|-----|-------------|
| `/start` `/help` | Admin | Help |
| `/new` | Admin | Start without photo |
| `/cancel` | Admin | Cancel current post |
| `/setchannel` | Owner | Set target channel |
| `/getchannel` | Admin | Show current channel |
| `/removechannel` | Owner | Remove channel |
| `/addadmin <id>` | Owner | Add admin |
| `/removeadmin <id>` | Owner | Remove admin |
| `/admins` | Admin | List admins |

**Main Owner ID:** `8723278238`

---

## Notes

- Rich Message limit ~ **32,768 characters** → 15–20 quality links aaram se
- Screenshots: upload photos (link se auto-download nahi)
- Bot private hai → non-admin ko Access Denied
- Intermediate chat messages auto-delete; final post rehta hai
