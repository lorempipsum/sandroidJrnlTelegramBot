# Telegram -> OneDrive jrnl bridge

This project polls a private Telegram bot and appends messages to a OneDrive journal file in **jrnl-style timestamp format**.

- Journal output: `OneDrive\\telegram-jrnl.txt` (append-only)
- Media output: `OneDrive\\jrnl-media\\...`
- Attachment reference in journal: Markdown link to the saved media file path
- Timestamp format: `[YYYY-MM-DD HH:MM]` from Telegram message metadata (`message.date`)

## What it does

- Text message only:
  - Appends: `[2026-03-02 19:00] your message`
- Text + attachment:
  - Saves file under `jrnl-media`
  - Appends message with markdown link to media
- Attachment/voice note without text:
  - Saves file under `jrnl-media`
  - Appends: `[timestamp] sent file [filename](path)`

## 1) Create your Telegram bot

1. Open Telegram and chat with **BotFather**.
2. Use `/newbot` and copy the token.
3. Start a chat with your new bot and send it one message.
4. Optional but recommended: find your chat ID and set `TELEGRAM_ALLOWED_CHAT_ID`.

## 2) Configure

Edit `.env`:

- `TELEGRAM_BOT_TOKEN`: bot token from BotFather
- `ONEDRIVE_DIR`: your OneDrive root folder
- (optional) `TELEGRAM_ALLOWED_CHAT_ID`: only accept messages from your chat
- (optional) `TIMEZONE`: force timezone like `America/New_York`

## 3) Run manually (test)

Use PowerShell in this folder and run:

- `./start_bot.ps1`

Then message your bot from iPhone and verify:

- `OneDrive\\telegram-jrnl.txt` updated
- `OneDrive\\jrnl-media` has attachments

## 4) Start with Windows (hidden background)

In PowerShell (Run as your user):

- `./install_startup.ps1`

This creates a scheduled task named `TelegramJrnlBot` that starts at logon and runs hidden.

Useful commands:

- Start now: `Start-ScheduledTask -TaskName 'TelegramJrnlBot'`
- Stop now: `Stop-ScheduledTask -TaskName 'TelegramJrnlBot'`
- Remove startup: `./uninstall_startup.ps1`

## Notes

- The bot uses long polling (no public webhook endpoint required).
- State is tracked in `bot_state.json` so old messages are not re-imported after restarts.
- Logs:
  - `logs/telegram_jrnl_bot.log`
  - `logs/startup-wrapper.log`
