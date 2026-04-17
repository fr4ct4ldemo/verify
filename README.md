# Bonzify

A modern Discord verification bot with hCaptcha integration, built with discord.py and hosted on Vercel.

---

> ⚠️ **Note:** This bot is intended for server verification purposes only. Do not use this bot to harass, restrict, or harm users in any way. The owner/admin is solely responsible for how this bot is used in their server.

---

## Disclaimer

Bonzify is an open source project provided as-is for legitimate Discord server verification use cases. The developers are not responsible for any misuse of this bot. By using Bonzify, you agree to comply with Discord's Terms of Service and Community Guidelines.

---

## Features

- hCaptcha verification via a hosted web page
- Auto role assignment on successful verification
- Session timeout and retry limit system
- Consistent embed color system (green, red, orange, blue)
- Detailed verification logs
- Slash commands: /verify and /setup

---

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your values
4. Deploy the web server to Vercel
5. Invite the bot to your server and run `/setup`

---

## Environment Variables

```env
BOT_TOKEN=
HCAPTCHA_SECRET_KEY=
HCAPTCHA_SITE_KEY=
BASE_URL=
```

---

## Deploying to Vercel

1. Push the project to GitHub
2. Import the repo in your Vercel dashboard
3. Add all environment variables in project settings
4. Deploy and copy the deployment URL to BASE_URL

---

## License

MIT License
