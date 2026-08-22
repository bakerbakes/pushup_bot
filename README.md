# pushup_bot

A Discord bot that runs a 100-day, server-wide push-up challenge:
members opt in, log sets throughout the day, and get called out
(nicely) when they hit 100 for the day.

## How it works

- The bot has a single, **bot-wide 100-day lifespan** — it's not
  per-server. Day 1 starts 24 hours after the bot's first-ever
  deploy, and the same countdown applies to every server it's in,
  no matter when that server added it.
- `/pushupjoin` — opt in. Optionally pick your timezone (Eastern,
  Central, Mountain, or Pacific) so your daily reset lines up with
  your day instead of the server's; defaults to UTC if skipped.
- `/pushuptimezone` — set or update your timezone after joining.
- `/pushuplog <count>` — log a set (any size, as many times a day as
  you want). Crossing 100 for the day (in your own timezone) triggers
  a celebration message + gif. Every log also adds to your lifetime
  total, with occasional milestone shout-outs (500, 1000, 2500, 5000,
  10000).
- `/pushuptoday` — check your count for today.
- `/pushuptotal` — check your lifetime total and what day of the 100
  it is.
- `/pushupscoreboard` — see every participant ranked by lifetime
  total, alongside their daily average (lifetime total ÷ days since
  they joined, in their own timezone).
- `/pushupsetchannel` — (needs "Manage Server") pick which channel
  gets inactivity check-ins. If nobody sets this, it defaults to
  whichever channel the first person ran `/pushupjoin` in.

**Inactivity check-ins:** once a day the bot scans everyone who's
joined. Anyone with no logged push-ups in 5+ days (counted in their
own timezone) gets a public `@mention` with a "you ok bro?" style
nudge in the check-in channel. It re-nags every additional 5 days of
continued silence (day 5, 10, 15...), not every single day, so it
stays a nudge rather than spam.

**Day 100 — self-destruct:** once the bot-wide countdown hits day
100, the bot posts a one-time explosion gif in every server (its
reminder channel, or the first channel it can send in) and then goes
permanently inert — every command replies that the challenge is over.
It stays online/connected; it just stops doing anything.

Data is stored in a local SQLite file (`pushup_bot.db` by default),
so there's no external database to set up.

## Setup

1. **Create the bot in Discord's developer portal**
   - Go to https://discord.com/developers/applications → New Application.
   - Under **Bot**, click "Add Bot", then copy the token.
   - Under **Bot** settings, no privileged intents are required for
     this bot (it only uses slash commands).
   - Under **OAuth2 → URL Generator**, check scopes `bot` and
     `applications.commands`, and under bot permissions check at
     least "Send Messages" and "Use Slash Commands". Use the
     generated URL to invite the bot to your server.

2. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

3. **Configure the token**
   ```
   cp .env.example .env
   ```
   Then edit `.env` and paste your bot token in place of
   `your-bot-token-here`.

4. **Run it**
   ```
   python bot.py
   ```
   On first run it registers the slash commands with Discord — this
   can take up to an hour to show up globally the very first time,
   though it's usually much faster. If you want instant updates
   while testing, sync commands to a single test guild instead (see
   "Faster testing" below).

## Faster testing (optional)

Global slash command sync can be slow to propagate. For instant
updates during development, sync to one guild instead by replacing
the sync call in `bot.py`:

```python
# instead of: synced = await bot.tree.sync()
guild = discord.Object(id=YOUR_TEST_GUILD_ID)
bot.tree.copy_global_to(guild=guild)
synced = await bot.tree.sync(guild=guild)
```

## About the gifs

The bot pulls a **live gif from GIPHY** on every daily-goal
celebration, and falls back to a small static list in `messages.py`
(`GIFS`) if no key is set or the live call fails for any reason — a
bad network blip should never block someone's push-up log. (Tenor's
API was shut down by Google as of mid-2026, which is why this uses
GIPHY instead.)

### Getting a GIPHY API key (free)

1. Go to https://developers.giphy.com/ and log in / sign up.
2. Click **Dashboard**, then **Create an App**.
3. Choose **API** (not SDK), give it a name (e.g. "pushup-bot"),
   and create it.
4. Copy the key it gives you.
5. Paste it into `.env` as `GIPHY_API_KEY=your-key-here`.

That's it — no further approval needed to start. New keys are
"beta" keys, rate-limited to 100 API calls/hour, which is far more
than a push-up bot will ever use (it only calls out on a daily-goal
celebration, at most a handful of times a day). GIPHY does ask that
apps using their API display "Powered By GIPHY" attribution
somewhere in the experience -- worth keeping in mind if you ever
turn this into something more public-facing than a personal server
bot.

If you leave `GIPHY_API_KEY` blank in `.env`, the bot just uses the
static `GIFS` list every time — no code changes needed either way.

## Keeping messaging fresh over 100 days

All response text lives in `messages.py` as plain Python lists —
`JOIN_MESSAGES`, `LOG_ACK_MESSAGES`, `DAILY_GOAL_MESSAGES`,
`GOAL_FLAVOR_ADDENDA`, and `TOTAL_MILESTONE_MESSAGES`. The bot picks
randomly from these each time, so the bigger you make the lists, the
less repetitive it feels over a 100-day run. No code changes needed
elsewhere — just add more lines.

## Notes / things to decide as you go

- Right now the challenge is **per-user opt-in**, not mandatory for
  the whole server — anyone can join anytime with `/pushupjoin`,
  even after day 1.
- The bot doesn't currently post automatic daily reminders — that
  wasn't in scope here, but would be a straightforward addition (a
  `discord.ext.tasks` loop) if you want it later.
- Timezone selection is limited to the four US zones (Eastern,
  Central, Mountain, Pacific) via `/pushupjoin` / `/pushuptimezone`;
  anyone outside those stays on UTC unless you widen the choice list
  in `bot.py` (`TIMEZONE_CHOICES`).
- After day 100, the bot self-destructs once (gif + goes inert) and
  stays that way — there's currently no way to "revive" it short of
  clearing the `destructed` flag in the `bot_state` table and
  restarting.

## Deploying it long-term

For running this 24/7 on a free VM (Oracle Cloud Always Free, Google
Cloud e2-micro Always Free), see **DEPLOY.md** — it walks through
setup, a systemd service so the bot survives reboots and crashes,
and keeping `pushup_bot.db` persistent on disk.

### Deploying on Wispbyte

Wispbyte is a panel host (Pterodactyl-style) rather than a raw VM, so
none of the systemd/VM steps in DEPLOY.md apply here -- the panel
handles process supervision itself.

1. **Upload only the code the bot needs to run:**
   - `bot.py`, `db.py`, `messages.py`, `requirements.txt`
   - `requirements.txt` must keep that exact lowercase name and sit
     in the same folder as `bot.py`, or Wispbyte won't detect it and
     auto-install the dependencies.
   - Don't upload `venv/`, `__pycache__/`, `pushup_bot.db`, `.git/`,
     `DEPLOY.md`, or `pushup_bot.service` -- none of that belongs on
     a panel host. `venv/` and `pushup_bot.db` get recreated
     automatically (Wispbyte manages its own Python environment from
     `requirements.txt`; the DB is created fresh by `init_db()` on
     first run, which also means the 100-day clock starts counting
     from whenever you first boot it there).
2. **Set the secrets directly on the panel, not from git** (your
   `.env` is correctly excluded from the repo, so it won't come along
   with a git-based deploy):
   - If Wispbyte's panel has a **Startup Variables** tab, set
     `DISCORD_TOKEN` (and `GIPHY_API_KEY` if you're using one) there.
   - Otherwise, create a new `.env` file directly in Wispbyte's file
     manager and fill it in the same way as `.env.example`.
3. **Set the startup command** to `python bot.py`.

**Known gotcha:** SQLite's default journal mode can throw a `disk I/O
error` on Wispbyte's container filesystem (WAL-style journaling needs
shared-memory file locking that doesn't work reliably there). `db.py`
already works around this by setting `PRAGMA journal_mode=MEMORY` on
every connection, so this shouldn't bite you -- worth knowing about if
you ever see that error after changing `db.py`, since it's easy to
reintroduce by dropping that pragma.
