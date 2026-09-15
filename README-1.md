# SKxPoster Bot (`@SKxPosterBot`)

Private Telegram bot for creating stylish Movie / Web Series / Episode posts with quality links, trailers, multiple stream links, and professional DMCA disclaimer.

---

## Features

- **Private only** — Owner + Admins only
- **Poster support**
  - Upload photo
  - Or send direct Image URL (TMDB / any .jpg/.png)
  - Or start without poster (`/new`)
- **Content Types**
  - Movie
  - Web Series (Multi-Season support)
  - Episode / Show
- **Optional fields**
  - Sample Link
  - Trailer Link
  - Multiple Watch / Stream Links (with ads note)
- **Quality Links**
  - Default: 480p, 720p HEVC, 720p x264, 1080p HEVC, 1080p x264, HQ-Rip 1080p, HQ 1080p
  - Add custom quality anytime
  - Only qualities with links appear in final post
  - 1 or 2 download links per quality
- **Web Series Multi-Season**
  - Add Season 1 → qualities → Season 2 → qualities… → Finish All
- **DMCA & Content Disclaimer**
  - Short text in every post
  - Clickable title opens full professional disclaimer poster
- **Hashtags** (optional)
- **Auto-cleanup**
  - All intermediate messages (inputs, buttons, preview) are deleted after final post
  - Only the final post remains in chat
- **Multi-Admin system**
  - Main owner can add/remove admins
- **Render + UptimeRobot ready** (free tier, no sleep)

---

## Owner ID
Main Owner: `8723278238`

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + quick guide |
| `/help` | Help |
| `/new` | Start new post without photo |
| `/cancel` | Cancel current process |
| `/addadmin <user_id>` | Add new admin (Owner only) |
| `/removeadmin <user_id>` | Remove admin (Owner only) |
| `/admins` | List all admins |

---

## How to Use the Bot

### Start a new post (3 ways):
1. **Upload a poster** (photo)
2. **Send Poster Image URL** (e.g. TMDB link)
3. **Send `/new`** (no poster)

### Step-by-step flow:

1. Select Type → **Movie / Web Series / Episode**
2. Title
3. Sample Link (optional – Skip available)
4. Trailer Link (optional – Skip available)
5. Watch / Stream Link(s)
   - Add one or multiple stream links
   - After each link → “Add Another” or “Done”
6. **If Web Series**:
   - Enter Season number
   - Add qualities for that season
   - “Add Another Season” or “Finish All Seasons”
7. **If Movie / Episode**:
   - Add quality links directly
8. Hashtags (optional)
9. Preview → Confirm
10. Final post is sent + all intermediate messages are auto-deleted

---

## Final Post Structure (Example)

```
🎬 𝗧𝗜𝗧𝗟𝗘
"Movie / Series Name"

📺 Season 01 • Episode 05          ← only for Episode

🎞️ 𝗦𝗔𝗠𝗣𝗟𝗘
🔗 Sample Link

🎬 𝗧𝗥𝗔𝗜𝗟𝗘𝗥
🔗 Watch Trailer

▶️ 𝗪𝗔𝗧𝗖𝗛 / 𝗦𝗧𝗥𝗘𝗔𝗠
🔗 Stream Link 1
🔗 Stream Link 2

⚠️ Note: Online streams may contain ads (few or many). We do not control third-party players or ads.

━━━━━━━━━━━━━━━━━━━━

📥 𝗔𝗟𝗟 𝗤𝗨𝗔𝗟𝗜𝗧𝗬 𝗟𝗜𝗡𝗞𝗦

🔹 480p
📦 Size: "1.2 GB"
🔗 Download Link 1
🔗 Download Link 2

🔹 720p HEVC
...

━━━━━━━━━━━━━━━━━━━━

🌐 𝗢𝗨𝗥 𝗢𝗧𝗛𝗘𝗥 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦

🎥 Movies | Web Series | Shows
👉 @MoviesWebSeries_08

🔗 MOVIE LINKS
👉 @Movielink_08

🤖 𝐑𝐄𝐐𝐔𝐄𝐒𝐓 𝐁𝐎𝐓
👉 @SKxMOVIES_RequestBot

💭 𝐎𝐏𝐄𝐍 𝐂𝐇𝐀𝐓
👉 @New_Movie_Chat

👑 SKxMOVIES
👉 @SKxMOVIES

📢 THE SK08
👉 @The_Sk08

━━━━━━━━━━━━━━━━━━━━

⚖️ 𝗗𝗠𝗖𝗔 & 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗜𝗦𝗖𝗟𝗔𝗜𝗠𝗘𝗥   ← clickable (opens full poster)

We do not host or store any files. All links are from third-party sources.
For takedown requests → @SKxMOVIES_RequestBot

━━━━━━━━━━━━━━━━━━━━

🔔 𝗦𝗧𝗔𝗬 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 • 𝗦𝗧𝗔𝗬 𝗨𝗣𝗗𝗔𝗧𝗘𝗗 🚀

#Hashtags
```

---

## Deploy on Render (Free)

### 1. Create Bot on Telegram
- Go to [@BotFather](https://t.me/BotFather)
- `/newbot`
- Name: `SKxPoster`
- Username: `SKxPosterBot`
- Copy the **BOT_TOKEN**

### 2. GitHub
1. Create a new repository
2. Upload these files:
   - `bot.py`
   - `requirements.txt`
   - `README.md`
   - `admins.json` (optional)

### 3. Render Setup
1. Go to [https://dashboard.render.com](https://dashboard.render.com)
2. **New → Web Service**
3. Connect your GitHub repo
4. Settings:
   - **Name**: `skxposter-bot` (any name)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Instance Type**: Free
5. **Environment Variables**:
   - Key: `BOT_TOKEN`  
     Value: `your_bot_token_here`
6. Click **Create Web Service**

### 4. UptimeRobot (Keep Alive)
1. Go to [https://dashboard.uptimerobot.com](https://dashboard.uptimerobot.com)
2. Add New Monitor
   - Monitor Type: **HTTP(s)**
   - Friendly Name: `SKxPoster Bot`
   - URL: `https://your-service-name.onrender.com`
   - Monitoring Interval: **5 minutes**
3. Save

Bot will stay awake on free tier.

---

## Local Testing (Optional)

```bash
pip install -r requirements.txt
export BOT_TOKEN="your_token_here"
python bot.py
```

---

## Notes

- Admins are saved in `admins.json`
- Caption uses HTML → links appear blue & clickable
- Only qualities that have at least one link are shown
- Stream links support multiple entries
- DMCA title is clickable and opens the full professional disclaimer image
- All intermediate chat messages are automatically cleaned after final post

---

Made for private use only.  
Channels: @MoviesWebSeries_08 | @SKxMOVIES | @The_Sk08
