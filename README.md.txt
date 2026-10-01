# 🤖 My First Telegram Bot

A multi-feature Telegram bot built with Python.

## ✨ Features

- 🍅 **Pomodoro Timer** — Custom work/break sessions with live countdown
- 📄 **Image → PDF** — Send photos, get a combined PDF
- 🖼 **PDF → Image** — Send a PDF, get each page as an image

## 🛠 Tech Stack

- Python 3
- python-telegram-bot
- img2pdf, PyMuPDF

## 🚀 Commands

| Command | Description |
|---------|-------------|
| `/start` | Show help menu |
| `/pomodoro` | Start 25 min work / 5 min break |
| `/pomodoro 50 10` | Custom work/break time |
| `/stop` | Cancel running timer |
| `/pdf` | Combine collected photos into PDF |
| `/clearpdf` | Clear collected photos |

## 📦 Setup

1. Clone this repo
2. Install dependencies: `pip install -r requirements.txt`
3. Set your bot token as an environment variable: `TOKEN=your_token_here`
4. Run: `python bot.py`

## 📜 License

MIT