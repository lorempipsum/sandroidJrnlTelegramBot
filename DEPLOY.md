Deploying Telegram Jrnl Bot to a Linux Droplet (DigitalOcean)

This repository supports two simple modes for storing the journal and attachments:

- Local OneDrive-synced folder (ONEDRIVE_DIR) — the script writes directly into a folder which is kept in sync by your OS OneDrive client (Windows/macOS).
- rclone remote (ONEDRIVE_REMOTE) — the script stages files locally and uploads them to OneDrive using rclone. This is the recommended, simplest approach for a headless Linux droplet.

The rclone approach requires no FUSE mount and works well when you want a small, reliable push-based sync.

1) Install rclone on the droplet

On Debian/Ubuntu, the quick way:

```bash
curl https://rclone.org/install.sh | sudo bash
```

Or follow instructions at https://rclone.org/install/ for your distro.

2) Configure an OneDrive remote

Run the interactive config and create a remote (example name: "onedrive"):

```bash
rclone config
# follow prompts, create a new remote, choose 'onedrive' as the provider
```

If your droplet has no browser, you can use `rclone authorize "onedrive"` on a machine with a browser and transfer the resulting token to the droplet, or use the `rclone config` flow which offers copy-paste authentication.

Test the remote (replace `onedrive` with your remote name):

```bash
rclone lsd onedrive:
```

3) Prepare the bot directory and .env

On the droplet, place the repository (for example in /home/ubuntu/sandroidJrnlTelegramBot). Create a `.env` file in the same directory with the following minimum contents:

```
TELEGRAM_BOT_TOKEN=123456:ABCdefGhI_jkl
ONEDRIVE_REMOTE=onedrive:jrnl
# Optionally, if you prefer a local OneDrive mount instead of rclone, set ONEDRIVE_DIR instead.
JOURNAL_FILE_NAME=telegram-jrnl.txt
MEDIA_SUBDIR=jrnl-media
POLL_TIMEOUT_SECONDS=30
POLL_INTERVAL_SECONDS=2
# Optional
TELEGRAM_ALLOWED_CHAT_ID=
TIMEZONE=
```

- `ONEDRIVE_REMOTE` should be the rclone remote and optional path (e.g. `onedrive:jrnl` will upload into the `jrnl` folder on OneDrive). The bot will create a small local staging directory `.onedrive_local` in the repository and upload files there.
- If you instead set `ONEDRIVE_DIR`, the bot will write directly to the given path (useful if you mount OneDrive via rclone mount or have a native OneDrive client).

4) Run the bot

The script uses only the Python standard library, so you can run directly with the system Python 3:

```bash
cd /home/ubuntu/sandroidJrnlTelegramBot
python3 telegram_jrnl_bot.py
```

5) Run as a systemd service (recommended)

Create `/etc/systemd/system/telegram_jrnl.service` (update paths and user):

```ini
[Unit]
Description=Telegram Jrnl Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/sandroidJrnlTelegramBot
EnvironmentFile=/home/ubuntu/sandroidJrnlTelegramBot/.env
ExecStart=/usr/bin/python3 /home/ubuntu/sandroidJrnlTelegramBot/telegram_jrnl_bot.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Reload systemd and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now telegram_jrnl.service
sudo journalctl -u telegram_jrnl -f
```

If you edit `.env` later (for example `JOURNAL_FILE_NAME`), restart the service to apply the new values:

```bash
sudo systemctl restart telegram_jrnl.service
```

6) Notes and behaviour

- When `ONEDRIVE_REMOTE` is used, attachments are uploaded to `<remote>/<path>/jrnl-media/<filename>` and the journal file is uploaded to `<remote>/<path>/<JOURNAL_FILE_NAME>`.
- The markdown links inserted into the journal are relative paths such as `jrnl-media/<filename>` so that when you open the journal file inside a synced OneDrive folder on your desktop the links point to the uploaded attachments.
- If you need shareable public links for attachments, that requires calling the Microsoft Graph API. rclone only uploads files and does not by itself create share links.
- You can switch to Google Drive later by creating a different rclone remote (e.g. `gdrive:`) and updating `ONEDRIVE_REMOTE`.

Troubleshooting

- If you see `rclone not found in PATH` in the logs, double-check rclone installation and that the `rclone` binary is on the PATH for the user running the service.
- If authentication with OneDrive fails, re-run `rclone config` and test with `rclone lsf <remote>:` from the droplet.

That's it — this approach keeps the bot simple on the server and uses rclone to handle OneDrive integration with minimal setup.
