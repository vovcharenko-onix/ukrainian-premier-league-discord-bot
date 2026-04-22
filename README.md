# Ukrainian Premier League Discord Bot

Discord bot for the Ukrainian Premier League. It scrapes data from `upl.ua` and supports:

- `/table` - full UPL standings
- `/attackers` - UPL scorers table
- `/today` - today's matches
- `/current` - current tour for the Kyiv playing week (`Tuesday -> Monday`)
- `/next` - next tour
- automatic daily posting of today's matches at **12:00 Europe/Kyiv**

## Caching

The bot now keeps a **daily disk cache** for:

- `/attackers`
- `/today`
- `/current`
- `/next`
- the scheduled daily `/today`-style post

The cache is stored in:

```text
~/.cache/ukrainian-premier-league-discord-bot/upl-pages
```

Each cached `upl.ua` page is reused until the Kyiv date changes, then the bot refreshes it automatically. This keeps RAM usage low because the bot stores the cached payloads on disk instead of holding them in memory between requests.

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```env
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_DAILY_MATCHES_CHANNEL_ID=123456789012345678
DISCORD_GUILD_ID=123456789012345678
```

### Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `DISCORD_BOT_TOKEN` | Yes | Discord bot token |
| `DISCORD_DAILY_MATCHES_CHANNEL_ID` | Yes | Channel for the daily 12:00 Kyiv post |
| `DISCORD_GUILD_ID` | No | Server ID for immediate slash-command sync |

If `DISCORD_GUILD_ID` is set, commands are synced only to that server, which is useful during development and helps avoid duplicate guild/global command entries.

## Local run

Install dependencies and run:

```bash
uv sync
uv run ukrainian-premier-league-discord-bot
```

## VPS deployment

These steps assume a Linux VPS with `systemd` available.

### 1. Install system packages

For Ubuntu / Debian:

```bash
sudo apt update
sudo apt install -y curl git
```

### 2. Install `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart the shell or load the profile:

```bash
source ~/.zshrc
```

If you use `bash`, load `~/.bashrc` instead.

### 3. Clone the project

```bash
git clone https://github.com/vovcharenko-onix/ukrainian-premier-league-discord-bot.git
cd ukrainian-premier-league-discord-bot
```

### 4. Install Python and dependencies

```bash
uv python install 3.14
uv sync --frozen
```

### 5. Create the environment file

```bash
cp .env.example .env
nano .env
```

Fill in:

- `DISCORD_BOT_TOKEN`
- `DISCORD_DAILY_MATCHES_CHANNEL_ID`
- optionally `DISCORD_GUILD_ID`

### 6. Test the bot manually

```bash
uv run ukrainian-premier-league-discord-bot
```

If the bot logs in successfully, stop it with `Ctrl+C` and continue with the service setup.

## Run as a `systemd` service

Create a service file:

```bash
sudo nano /etc/systemd/system/upl-discord-bot.service
```

Use this template and replace `<user>` and `<project-path>`:

```ini
[Unit]
Description=Ukrainian Premier League Discord Bot
After=network.target

[Service]
Type=simple
User=<user>
WorkingDirectory=<project-path>
Environment=HOME=/home/<user>
ExecStart=/home/<user>/.local/bin/uv run ukrainian-premier-league-discord-bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Example project path:

```text
/home/<user>/ukrainian-premier-league-discord-bot
```

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable upl-discord-bot
sudo systemctl start upl-discord-bot
```

Check status:

```bash
sudo systemctl status upl-discord-bot
```

View logs:

```bash
journalctl -u upl-discord-bot -f
```

## Updating on the VPS

When you deploy a new version:

```bash
cd /home/<user>/ukrainian-premier-league-discord-bot
git pull
uv sync --frozen
sudo systemctl restart upl-discord-bot
```

## Notes

- The daily automatic post is skipped if there are no matches for that date.
- Slash command updates can take time if you do not use `DISCORD_GUILD_ID`.
- The bot scrapes `upl.ua`; if the site markup changes, parsing logic may need updates.
