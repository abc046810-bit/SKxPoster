# SKxPoster Bot (`@SKxPosterBot`)

Private Telegram bot for creating stylish Movie / Web Series / Episode posts with quality links.

## Features

- Only Owner + Admins can use
- Send poster → select type → title → optional sample → quality links
- Dynamic quality add
- Stylish HTML caption (exactly matching your format)
- Multi-admin support
- Render free tier ready + UptimeRobot keep-alive

## Owner ID
Main Owner: `8723278238`

## Commands

- `/start` - Start / Help
- `/help` - Help
- `/cancel` - Cancel current process
- `/addadmin <user_id>` - Add new admin (only main owner)
- `/removeadmin <user_id>` - Remove admin (only main owner)
- `/admins` - List all admins

## How to use the bot

1. Send any poster/image
2. Select: Movie / Web Series / Episode
3. Send Title
4. Sample Link (or Skip)
5. If Episode → Season + Episode number
6. Click on qualities → enter Size + Link1 + Link2 (optional)
7. You can also "Add New Quality"
8. Click **Finish & Continue**
9. Hashtags bhejo (optional) ya Skip
10. Preview aayega → Confirm → Final post aapko private mein mil jayega

---

## Deploy on Render (Free)

### 1. Create Bot
- Go to @BotFather → `/newbot`
- Name: `SKxPoster`
- Username: `SKxPosterBot`
- Copy the **BOT_TOKEN**

### 2. GitHub
1. Create a new repository on GitHub
2. Upload these files:
   - `bot.py`
   - `requirements.txt`
   - `README.md`
3. (Optional) Create empty `admins.json` with content:
   ```json
   {"admins": [8723278238]}
   ```

### 3. Render Setup
1. Go to [https://dashboard.render.com](https://dashboard.render.com)
2. **New → Web Service**
3. Connect your GitHub repo
4. Settings:
   - **Name**: `skxposter-bot` (or anything)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Instance Type**: Free
5. **Environment Variables**:
   - Key: `BOT_TOKEN`  
     Value: `your_bot_token_from_botfather`
6. Click **Create Web Service**

### 4. UptimeRobot (Keep Alive)
1. Go to [https://dashboard.uptimerobot.com](https://dashboard.uptimerobot.com)
2. Add New Monitor
   - Monitor Type: **HTTP(s)**
   - Friendly Name: `SKxPoster Bot`
   - URL: `https://your-render-service-name.onrender.com`
   - Monitoring Interval: **5 minutes**
3. Save

Bot ab sleep nahi hoga.

---

## Local Testing (Optional)

```bash
pip install -r requirements.txt
export BOT_TOKEN="your_token_here"
python bot.py
```

---

## Notes

- Admins are saved in `admins.json` (persists on Render disk temporarily, better to re-add after major restart if needed)
- Caption uses HTML → links appear blue automatically
- If no link in a quality → shows "🔜 Added Soon"
- Sample link completely removed from caption if skipped

Made for private use only.
