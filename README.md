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

  ## Running on Linux / DigitalOcean (simple options)

  This repository is cross-platform. On a Linux droplet the easiest ways to have the bot write into OneDrive are:

  A) Mount your OneDrive with rclone and point `ONEDRIVE_DIR` at the mountpoint (recommended).

  - Install rclone: `curl https://rclone.org/install.sh | sudo bash` (or use your package manager).
  - Run `rclone config` and create a remote called e.g. `onedrive` following the interactive prompts.
  - Mount the remote (temporary):

  ```sh
  rclone mount onedrive: /mnt/onedrive --daemon
  ```

  - Set `ONEDRIVE_DIR=/mnt/onedrive` in `.env` and run the bot (see systemd below).

  B) Or keep a local folder and let the bot push files using rclone after every write.

  - Set `ONEDRIVE_REMOTE` in `.env` to the rclone remote prefix you created, e.g. `onedrive:my-jrnl`.
  - The bot will call `rclone copyto` to upload attachments and the journal file after each change.
  - Optionally set `RCLONE_REMOVE_LOCAL=true` to delete local media files after a successful upload (saves disk space on the server).

  Example minimal `.env` (see `.env.example` in the repo):

  ```
  TELEGRAM_BOT_TOKEN="<your-token>"
  ONEDRIVE_DIR="/home/youruser/sandroidJrnlTelegramBot/onedrive"
  # Optional rclone upload instead of a mount
  # ONEDRIVE_REMOTE="onedrive:telegram-jrnl"
  # RCLONE_REMOVE_LOCAL=false
  # Optional: TELEGRAM_ALLOWED_CHAT_ID=123456789
  # Optional: TIMEZONE=Europe/Berlin
  ```

  Systemd unit example (copy to `/etc/systemd/system/telegram-jrnl.service` and edit `User` and `WorkingDirectory`):

  ```
  [Unit]
  Description=Telegram Jrnl Bot
  After=network-online.target

  [Service]
  Type=simple
  User=youruser
  WorkingDirectory=/home/youruser/sandroidJrnlTelegramBot
  EnvironmentFile=/home/youruser/sandroidJrnlTelegramBot/.env
  ExecStart=/usr/bin/env python3 telegram_jrnl_bot.py
  Restart=on-failure
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```

  After adding the unit run:

  ```sh
  sudo systemctl daemon-reload
  sudo systemctl enable --now telegram-jrnl.service
  sudo journalctl -u telegram-jrnl -f
  ```

  Notes:
  - If you use an rclone mount, ensure the mount unit starts before this service (use `After=`/`Wants=` in the unit file).
  - The bot uses only the Python standard library; no extra pip packages are required unless you add them.
