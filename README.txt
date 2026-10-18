# Keepit — Telegram Bot

A multi-feature Telegram bot built with Python. Handles productivity and document conversion, deployed on Render with 24/7 uptime.

![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21.x-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Deploy](https://img.shields.io/badge/Deployed%20on-Render-purple)

---

## ✨ Features

### 🍅 Pomodoro Timer
- Customizable work and break durations
- Live countdown updated every second
- Cancel anytime with `/stop`

### 📄 Image → PDF
- Send multiple photos → receive one combined PDF
- Downloads photos in parallel for speed
- Works with 50–80 photos reliably

### 🖼 PDF → Image
- Send a PDF → receive pages as images
- Up to 20 pages → individual photos
- 21–200 pages → single ZIP file
- Cancel mid-conversion with `/stopconvert`

---

## 🚀 Commands

| Command | Description |
|---------|-------------|
| `/start` | Show the help menu |
| `/pomodoro` | Start 25 min work / 5 min break |
| `/pomodoro 50 10` | Custom work/break duration |
| `/stop` | Cancel a running Pomodoro timer |
| `/pdf` | Combine collected photos into one PDF |
| `/clearpdf` | Clear collected photos |
| `/stopconvert` | Cancel an ongoing conversion |

---

## 🛠 Tech Stack

- **Python 3** — core language
- **python-telegram-bot** — Telegram API wrapper
- **img2pdf** — Image → PDF conversion
- **PyMuPDF** — PDF → Image conversion
- **aiohttp** — Web server for Render + self-ping keep-alive
- **Render** — free 24/7 cloud hosting

---

## 📦 Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/keepit-telegram-bot.git
cd keepit-telegram-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your bot token (get one from @BotFather on Telegram)
# Windows:
set TOKEN=your_bot_token_here
# Linux/Mac:
export TOKEN=your_bot_token_here

# 4. Run the bot
python bot.py
☁️ Deployment (Render)
This bot is deployed on Render free tier.

Fork or clone this repo

Create a new Web Service on Render and connect this repo

Build Command: pip install -r requirements.txt

Start Command: python bot.py

Add environment variable: TOKEN = your_bot_token

Deploy 🚀 
Limitations (Free Tier)
Max 200 pages per PDF (larger files are rejected politely)

Max 20 MB PDF file size

~80 photos per Image → PDF conversion (memory limit)

2–3 concurrent users doing heavy conversions

Free Render tier has 512 MB RAM and 750 hours/month
