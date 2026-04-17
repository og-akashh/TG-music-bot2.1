# 🎵 Telegram Voice Chat Music Bot

A **production-grade**, fully modular Telegram bot that streams high-quality audio into Telegram voice chats. Built with Python 3.11, Pyrogram, PyTgCalls, and yt-dlp.

---

## ✨ Features

| Category | Details |
|---|---|
| **Sources** | YouTube (search + URL), Spotify (track / album / playlist), SoundCloud, direct audio URLs |
| **Queue** | Add, remove, shuffle, reorder, loop modes (off / single / queue), persistent via Redis |
| **Controls** | Play, Pause, Resume, Skip, Stop, Seek, Volume (1–200%), Audio Filters |
| **Audio Filters** | Bass Boost, Nightcore, Echo, 8D Audio, Earrape, Vaporwave, Karaoke |
| **UI** | Inline keyboard on Now Playing card, thumbnail generator, paginated queue |
| **Lyrics** | Genius API + web scrape fallback, auto-chunked for long songs |
| **Playlists** | Per-user save / load / list / delete (MongoDB-backed) |
| **Admin** | Role-based permissions (owner / admin / user), admin-only command lock |
| **Reliability** | Auto-reconnect on VC disconnect, multi-chat isolation, background cache eviction |
| **i18n** | English + Spanish (add any language via JSON file) |
| **Dashboard** | Optional FastAPI web panel with REST API and real-time controls |

---

## 🗂 Project Structure

```
music_bot/
├── bot/
│   ├── main.py                  # Application entry point
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # All config from environment variables
│   ├── handlers/
│   │   ├── __init__.py          # Registers all handlers with Pyrogram
│   │   ├── start.py             # /start, /help, /ping
│   │   ├── play.py              # /play (YouTube, Spotify, SoundCloud, search)
│   │   ├── controls.py          # /pause /resume /skip /stop /seek /volume /loop
│   │   ├── queue_handler.py     # /queue /shuffle /clearqueue /remove
│   │   ├── lyrics_handler.py    # /lyrics
│   │   ├── playlist_handler.py  # /playlist save|load|list|show|delete
│   │   ├── settings_handler.py  # /settings (inline config panel)
│   │   ├── callbacks.py         # All inline button callback queries
│   │   └── admin.py             # /adminadd /adminremove /stats /broadcast /leave
│   ├── player/
│   │   ├── __init__.py
│   │   ├── music_player.py      # Core voice-chat stream controller (singleton)
│   │   ├── queue_manager.py     # High-level queue operations
│   │   └── audio_filters.py     # ffmpeg filter presets
│   ├── services/
│   │   ├── __init__.py
│   │   ├── youtube.py           # yt-dlp search, extraction, caching
│   │   ├── spotify.py           # Spotify API + YouTube resolution
│   │   ├── soundcloud.py        # SoundCloud via yt-dlp
│   │   └── lyrics.py            # Genius API + scrape fallback
│   ├── database/
│   │   ├── __init__.py
│   │   ├── mongo.py             # Motor async MongoDB (users, playlists, history)
│   │   └── redis_client.py      # aioredis (queue, state, cache, rate-limit)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py            # Rich console + rotating file logger
│   │   ├── decorators.py        # @admin_only, @owner_only, @rate_limit, etc.
│   │   ├── formatters.py        # Duration, progress bar, inline keyboard builders
│   │   ├── thumbnail.py         # Pillow Now Playing card generator
│   │   └── cache_manager.py     # Disk cache LRU eviction
│   └── locales/
│       ├── i18n.py              # Translation loader
│       ├── en.json              # English strings
│       └── es.json              # Spanish strings
├── dashboard/
│   ├── __init__.py
│   ├── app.py                   # FastAPI REST API + uvicorn runner
│   └── templates/
│       └── index.html           # Dark-themed web control panel
├── generate_session.py          # Helper: generate Pyrogram string session
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── setup.sh                     # One-shot VPS installer
└── .gitignore
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | 3.11 recommended |
| ffmpeg | Any recent | Must be in `PATH` |
| MongoDB | 6.0+ | Local or Atlas |
| Redis | 7.0+ | Local or RedisCloud |

---

### Option A — Local Machine (Development)

```bash
# 1. Clone the repository
git clone https://github.com/yourname/music-bot.git
cd music-bot

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install ffmpeg
#    Ubuntu/Debian:  sudo apt install ffmpeg
#    macOS:          brew install ffmpeg
#    Windows:        https://ffmpeg.org/download.html

# 5. Configure environment
cp .env.example .env
nano .env                          # Fill in all values (see Configuration section)

# 6. Generate Pyrogram string session (userbot account)
python generate_session.py
# Copy the printed SESSION_STRING into your .env

# 7. Start the bot
python -m bot.main
```

---

### Option B — VPS (Ubuntu 22.04 LTS)

```bash
# Upload the project or clone it, then:
chmod +x setup.sh
sudo ./setup.sh

# Follow the on-screen instructions to fill in .env,
# then start the service:
systemctl start musicbot
journalctl -u musicbot -f        # follow logs
```

---

### Option C — Docker Compose (Recommended for Production)

```bash
# 1. Copy and fill in your .env
cp .env.example .env
nano .env

# 2. Build and start all services (bot + MongoDB + Redis)
docker compose up -d

# 3. Follow bot logs
docker compose logs -f bot

# 4. Stop everything
docker compose down
```

---

## ⚙️ Configuration Reference

All settings live in `.env`. Every variable is documented in `.env.example`.

### Required Variables

| Variable | Description |
|---|---|
| `API_ID` | From [my.telegram.org](https://my.telegram.org) → API Development Tools |
| `API_HASH` | From [my.telegram.org](https://my.telegram.org) |
| `BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `SESSION_STRING` | Pyrogram user session (run `generate_session.py`) |
| `DB_URI` | MongoDB connection string |
| `REDIS_URL` | Redis connection URL |

### Optional Variables

| Variable | Default | Description |
|---|---|---|
| `OWNER_ID` | `0` | Your Telegram user ID (owner commands) |
| `LOG_CHANNEL` | `0` | Chat ID for startup/error logs |
| `SPOTIFY_CLIENT_ID` | `` | Spotify developer app credentials |
| `SPOTIFY_CLIENT_SECRET` | `` | Spotify developer app credentials |
| `GENIUS_API_TOKEN` | `` | For lyrics fetching |
| `MAX_QUEUE_SIZE` | `100` | Max tracks per queue |
| `MAX_CACHE_SIZE_MB` | `2048` | Disk cache limit in MB |
| `AUTO_PLAY` | `true` | Auto-play related songs when queue ends |
| `DASHBOARD_ENABLED` | `false` | Enable FastAPI dashboard |
| `DASHBOARD_SECRET` | `` | Bearer token protecting the dashboard |

---

## 🤖 Bot Setup on Telegram

### 1. Create a Bot
1. Message [@BotFather](https://t.me/BotFather)
2. `/newbot` → set a name and username
3. Copy the **token** → `BOT_TOKEN` in `.env`

### 2. Set Bot Commands (optional but recommended)
Send this to @BotFather → `/setcommands`:

```
play - Play a song or URL
pause - Pause playback
resume - Resume playback
skip - Skip to next track
stop - Stop and clear queue
seek - Seek to position
volume - Get or set volume
loop - Cycle loop mode
queue - Show current queue
shuffle - Shuffle the queue
clearqueue - Clear all queued tracks
remove - Remove a track from queue
lyrics - Get song lyrics
playlist - Manage saved playlists
settings - Chat settings panel
np - Now playing info
ping - Check bot latency
help - Show all commands
```

### 3. Create Userbot Session
The userbot is a **separate Telegram account** (not the bot account) that physically joins the voice chat.  
You can use an old personal account or a dedicated account.

```bash
python generate_session.py
```

Enter that account's phone number, the OTP, and optional 2FA password.  
Copy the printed `SESSION_STRING` into `.env`.

### 4. Add Bot to Your Group
1. Add the **bot** to your group as an admin with these permissions:
   - ✅ Delete messages
   - ✅ Invite users via link
2. Add the **userbot** to the group as a member.
3. Start a Voice Chat in the group.
4. Use `/play <song>` — the userbot will join and start streaming.

---

## 📋 Command Reference

### Playback

| Command | Description |
|---|---|
| `/play <query\|URL>` | Search YouTube or paste a YouTube/Spotify/SoundCloud URL |
| `/pause` | Pause the current track |
| `/resume` | Resume a paused track |
| `/skip` | Skip to the next queued track |
| `/stop` | Stop playback, leave VC, clear queue |
| `/seek <time>` | Jump to a position (`/seek 90` or `/seek 1:30`) |
| `/volume [1-200]` | Show or set volume percentage |
| `/loop` | Cycle: Off → Single Track → Full Queue → Off |
| `/np` or `/nowplaying` | Show current track info |

### Queue Management

| Command | Description |
|---|---|
| `/queue [page]` | List queued tracks (paginated) |
| `/shuffle` | Randomly reorder the queue |
| `/clearqueue` | Remove all tracks from the queue |
| `/remove <position>` | Remove track at position N from queue |

### Extras

| Command | Description |
|---|---|
| `/lyrics [query]` | Fetch lyrics for current or specified song |
| `/playlist list` | List your saved playlists |
| `/playlist save <name>` | Save current queue as a named playlist |
| `/playlist load <name>` | Load a playlist into the queue |
| `/playlist show <name>` | Show tracks inside a playlist |
| `/playlist delete <name>` | Delete a saved playlist |
| `/settings` | Open the settings panel (admins only) |
| `/ping` | Check bot latency and uptime |
| `/help` | Show the help message |

### Admin / Owner

| Command | Description |
|---|---|
| `/adminadd <user>` | Grant bot-admin to a user in this chat |
| `/adminremove <user>` | Revoke bot-admin from a user |
| `/stats` | Show DB and cache statistics (owner only) |
| `/broadcast <text>` | Message all registered chats (owner only, private) |
| `/clearcache` | Delete all cached audio files (owner only) |
| `/leave <chat_id>` | Force-leave a group (owner only, private) |

---

## 🎚 Audio Filters

Applied via the inline filter button on the Now Playing card, or via `/settings → Default Filter`:

| Filter | Effect |
|---|---|
| None | No processing (pass-through) |
| Bass Boost | Boosts low-frequency equalizer bands |
| Nightcore | Speeds up audio + pitch shift up |
| Echo | Adds reverb-echo effect |
| 8D Audio | Panning oscillator for headphone effect |
| Earrape | Extreme clipping / distortion |
| Vaporwave | Slows audio + pitch shift down |
| Karaoke | Removes center channel (vocals) |

---

## 🌐 Adding a New Language

1. Copy `bot/locales/en.json` to `bot/locales/<code>.json` (e.g. `fr.json`)
2. Translate all string values (keep the `{placeholder}` tokens as-is)
3. Users can change language via `/settings → Language` or by the bot auto-detecting `user.language_code`

---

## 🖥 Web Dashboard

When `DASHBOARD_ENABLED=true`:

- Open `http://your-server:8080/` in a browser
- Enter your `DASHBOARD_SECRET` token
- Control playback, view queue and statistics in real time

### REST API Endpoints

All endpoints require `Authorization: Bearer <DASHBOARD_SECRET>`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/stats` | Global bot statistics |
| `GET` | `/api/queue/{chat_id}` | Queue + now-playing for a chat |
| `POST` | `/api/skip/{chat_id}` | Skip current track |
| `POST` | `/api/stop/{chat_id}` | Stop playback |
| `POST` | `/api/pause/{chat_id}` | Pause playback |
| `POST` | `/api/resume/{chat_id}` | Resume playback |
| `POST` | `/api/volume/{chat_id}` | Set volume `{"volume": 80}` |

---

## 🏗 Architecture Notes

### Why a userbot?

PyTgCalls requires a **full Telegram client** (not just a bot) to join voice chats because Telegram's voice chat protocol (`GroupCall`) is only available to user accounts. The bot account handles commands; the userbot account does the audio streaming.

### Data flow for `/play`

```
User → /play <query>
         │
         ▼
    play.py handler
         │
    Detect source type
    ┌────┴──────────────────────────────────┐
    │ YouTube URL     │ Spotify URL          │ Search query
    ▼                 ▼                      ▼
youtube.get_track()  spotify.resolve_url()  youtube.search()
         │                   │
         └───────────────────┘
                  │
          Track dict (title, artist, duration, stream_url, …)
                  │
         queue_manager.add()  ──▶  Redis RPUSH
                  │
         music_player.play()
                  │
         pytgcalls.join_group_call()
                  │
         AudioPiped(stream_url)  ──▶  ffmpeg  ──▶  Telegram VC
```

### Redis key schema

| Key pattern | Type | Content |
|---|---|---|
| `queue:{chat_id}` | List | JSON-encoded track dicts |
| `np:{chat_id}` | String | JSON-encoded current track |
| `loop:{chat_id}` | String | `off` / `single` / `queue` |
| `vol:{chat_id}` | String | Volume integer (1-200) |
| `cache:{key}` | String | Generic JSON cache with TTL |
| `rl:{user_id}:{cmd}` | String | Rate-limit counter with TTL |

---

## 🔧 Troubleshooting

### Bot doesn't respond to commands

- Verify `BOT_TOKEN` is correct
- Make sure the bot is added to the group as an admin
- Check logs: `journalctl -u musicbot -f` or `docker compose logs -f bot`

### "No active stream" but music was playing

- The voice chat may have ended. Use `/play` again to restart.
- Check that the userbot is still a member of the group.

### Voice chat joins but no audio

- Confirm `ffmpeg` is installed: `ffmpeg -version`
- Confirm the stream URL isn't expired (yt-dlp URLs expire in ~6 hours; the bot re-fetches automatically but manual seeks after that window may fail).
- Try: `yt-dlp -f bestaudio "https://youtu.be/VIDEO_ID"` on the server to verify yt-dlp is working.

### Spotify tracks return no results

- Verify `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` are set in `.env`.
- Check [developer.spotify.com](https://developer.spotify.com) that your app is active.
- The bot maps Spotify → YouTube via search; very obscure tracks may not match well.

### Redis connection refused

```bash
# Check Redis is running
systemctl status redis-server

# Test connection
redis-cli ping   # Should return PONG
```

### MongoDB connection refused

```bash
# Check MongoDB is running
systemctl status mongod

# Test connection
mongosh --eval "db.adminCommand('ping')"
```

### SESSION_STRING errors / "User not authorised"

- The session belongs to the account that ran `generate_session.py`.
- If that account was logged out or the session revoked, re-run `generate_session.py`.
- Ensure the userbot account has NOT been banned from the target group.

### `pytgcalls` / `py-tgcalls` import errors

```bash
pip install --upgrade py-tgcalls
```

### Thumbnail generation fails (Pillow errors)

```bash
# Install system image libraries
sudo apt install libpng-dev libjpeg-dev libfreetype6-dev
pip install --force-reinstall Pillow
```

### Docker: "port already in use"

```bash
# Find and kill the process using port 8080
sudo lsof -ti :8080 | xargs kill -9
docker compose up -d
```

### High memory usage

- Lower `MAX_CACHE_SIZE_MB` in `.env`
- Run `make clean` or use the `/clearcache` command
- Reduce `MAX_QUEUE_SIZE`

---

## 📦 Deployment Guides

### Cloud Platforms (Railway / Render / Fly.io)

1. Push the repo to GitHub
2. Create a new project and connect the repo
3. Set all environment variables in the platform's dashboard
4. Set the start command: `python -m bot.main`
5. Add a MongoDB add-on (e.g. Railway's MongoDB plugin) or use MongoDB Atlas
6. Add a Redis add-on or use Redis Cloud

> **Note:** Free tiers on most cloud platforms will sleep your bot. Use a paid tier or keep-alive pings.

### VPS Scaling

For high-load deployments (many simultaneous chats):

- Run multiple bot instances pointing to the same Redis/MongoDB (stateless design)
- Use a Redis Sentinel or Cluster for Redis HA
- Use MongoDB Atlas with auto-scaling

---

## 🛡 Security Checklist

- [ ] `SESSION_STRING` stored only in `.env`, never in code or logs
- [ ] `.env` in `.gitignore` and never committed
- [ ] `DASHBOARD_SECRET` is a long random string (`python3 -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] MongoDB not exposed publicly (bind to localhost or use auth)
- [ ] Redis not exposed publicly (bind to localhost or use auth + TLS)
- [ ] Bot runs as a non-root user in Docker and on the VPS
- [ ] Log channel set to a private channel only you can see

---

## 📄 License

MIT License — see `LICENSE` for details.

---

## 🤝 Contributing

Pull requests are welcome! Please:
1. Fork the repo and create a feature branch
2. Follow the existing code style (type hints, docstrings, async patterns)
3. Test your changes with both single-track and playlist flows
4. Open a PR with a clear description
