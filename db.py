"""
Persistence layer for pushup_bot.

Uses a plain SQLite file so the bot needs zero external services.
Everything is keyed by (guild_id, user_id) so the bot can run in
multiple servers at once.

The 100-day challenge clock is global, not per-guild: it starts 24
hours after the bot's first-ever deploy (see bot_state.deploy_time)
and runs out once, for every server the bot is in.
"""

import sqlite3
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "pushup_bot.db")
CHALLENGE_LENGTH_DAYS = 100
DAILY_GOAL = 100


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                reminder_channel_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS participants (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                joined_date TEXT NOT NULL,
                total INTEGER NOT NULL DEFAULT 0,
                last_nagged_date TEXT,
                timezone TEXT NOT NULL DEFAULT 'UTC',
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_logs (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                log_date TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                goal_hit INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, log_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                deploy_time TEXT NOT NULL,
                destructed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Migrations for DBs created before these columns existed.
        for table, column, coltype in [
            ("guilds", "reminder_channel_id", "TEXT"),
            ("participants", "last_nagged_date", "TEXT"),
            ("participants", "timezone", "TEXT NOT NULL DEFAULT 'UTC'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            except sqlite3.OperationalError:
                pass  # column already exists

        # Set once, on the very first boot this DB file ever sees. The
        # 100-day challenge clock is anchored to this moment (+24h),
        # not to when any particular guild joined.
        conn.execute(
            "INSERT OR IGNORE INTO bot_state (id, deploy_time, destructed) "
            "VALUES (1, ?, 0)",
            (datetime.now(timezone.utc).isoformat(),),
        )


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    # WAL mode (tried first) needs shared-memory file locking that
    # doesn't work reliably on every container filesystem -- it caused
    # "disk I/O error" on this host. MEMORY journal mode instead keeps
    # SQLite's temporary rollback data in RAM rather than writing any
    # extra file to disk at all, avoiding this whole class of
    # filesystem-compatibility problem. Trade-off: if the process is
    # killed mid-write, that one write could be lost (rather than
    # cleanly rolled back) -- an acceptable risk for this bot's data.
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute("PRAGMA temp_store=MEMORY")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _local_date(tz_name: str) -> date:
    """Today's date in a given IANA timezone, falling back to UTC for
    an unknown/invalid zone name rather than raising."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def local_today(tz_name: str) -> date:
    return _local_date(tz_name)


# ---------- bot-wide 100-day lifespan ----------

def get_deploy_time() -> datetime:
    with _connect() as conn:
        row = conn.execute("SELECT deploy_time FROM bot_state WHERE id = 1").fetchone()
    return datetime.fromisoformat(row[0])


def get_challenge_start() -> datetime:
    """The day-1 anchor: 24 hours after the bot's first-ever deploy."""
    return get_deploy_time() + timedelta(hours=24)


def get_day_number() -> int:
    """1-indexed day of the bot's single, server-wide 100-day lifespan.
    Returns 0 during the 24-hour pre-launch buffer, before day 1 starts."""
    elapsed = datetime.now(timezone.utc) - get_challenge_start()
    if elapsed.total_seconds() < 0:
        return 0
    return elapsed.days + 1


def get_days_remaining() -> int:
    return max(0, CHALLENGE_LENGTH_DAYS - get_day_number())


def is_destructed() -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT destructed FROM bot_state WHERE id = 1").fetchone()
    return bool(row and row[0])


def mark_destructed():
    with _connect() as conn:
        conn.execute("UPDATE bot_state SET destructed = 1 WHERE id = 1")


# ---------- guilds ----------

def set_guild_start_if_missing(guild_id: int, start_date: str | None = None):
    """Ensures a guilds row exists (needed for reminder-channel storage).
    start_date is kept for schema compatibility but no longer drives the
    100-day countdown -- that's global now, see get_day_number()."""
    start_date = start_date or date.today().isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO guilds (guild_id, start_date) VALUES (?, ?)",
            (str(guild_id), start_date),
        )


def set_reminder_channel(guild_id: int, channel_id: int):
    with _connect() as conn:
        conn.execute(
            "UPDATE guilds SET reminder_channel_id = ? WHERE guild_id = ?",
            (str(channel_id), str(guild_id)),
        )


def set_reminder_channel_if_missing(guild_id: int, channel_id: int):
    with _connect() as conn:
        row = conn.execute(
            "SELECT reminder_channel_id FROM guilds WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()
        if row and row[0]:
            return
        conn.execute(
            "UPDATE guilds SET reminder_channel_id = ? WHERE guild_id = ?",
            (str(channel_id), str(guild_id)),
        )


def get_reminder_channel(guild_id: int) -> int | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT reminder_channel_id FROM guilds WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()
    return int(row[0]) if row and row[0] else None


# ---------- participants ----------

def join_user(guild_id: int, user_id: int, tz: str = "UTC") -> bool:
    """Returns True if this is a new signup, False if already joined."""
    with _connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM participants WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO participants (guild_id, user_id, joined_date, total, timezone) "
            "VALUES (?, ?, ?, 0, ?)",
            (str(guild_id), str(user_id), _local_date(tz).isoformat(), tz),
        )
        return True


def is_joined(guild_id: int, user_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM participants WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return row is not None


def get_user_timezone(guild_id: int, user_id: int) -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT timezone FROM participants WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return row[0] if row and row[0] else "UTC"


def set_user_timezone(guild_id: int, user_id: int, tz: str) -> bool:
    """Returns True if the user was joined (and updated), False otherwise."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE participants SET timezone = ? WHERE guild_id = ? AND user_id = ?",
            (tz, str(guild_id), str(user_id)),
        )
        return cur.rowcount > 0


def add_pushups(guild_id: int, user_id: int, count: int):
    """
    Logs a set for "today" in the user's own timezone. Returns a dict with:
      today_total, grand_total, day_number, days_remaining, crossed_goal_today
    crossed_goal_today is True only the moment the daily total crosses
    100 for the first time that day (so we don't spam the goal message).
    """
    today = _local_date(get_user_timezone(guild_id, user_id)).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT count, goal_hit FROM daily_logs "
            "WHERE guild_id = ? AND user_id = ? AND log_date = ?",
            (str(guild_id), str(user_id), today),
        ).fetchone()
        before = row[0] if row else 0
        already_hit = bool(row[1]) if row else False
        after = before + count

        crossed = (not already_hit) and after >= DAILY_GOAL

        if row:
            conn.execute(
                "UPDATE daily_logs SET count = ?, goal_hit = ? "
                "WHERE guild_id = ? AND user_id = ? AND log_date = ?",
                (after, 1 if (already_hit or crossed) else 0,
                 str(guild_id), str(user_id), today),
            )
        else:
            conn.execute(
                "INSERT INTO daily_logs (guild_id, user_id, log_date, count, goal_hit) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(guild_id), str(user_id), today, after, 1 if crossed else 0),
            )

        conn.execute(
            "UPDATE participants SET total = total + ? "
            "WHERE guild_id = ? AND user_id = ?",
            (count, str(guild_id), str(user_id)),
        )
        total_row = conn.execute(
            "SELECT total FROM participants WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
        grand_total = total_row[0] if total_row else count

    return {
        "today_total": after,
        "grand_total": grand_total,
        "day_number": get_day_number(),
        "days_remaining": get_days_remaining(),
        "crossed_goal_today": crossed,
    }


def get_today_total(guild_id: int, user_id: int) -> int:
    today = _local_date(get_user_timezone(guild_id, user_id)).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT count FROM daily_logs "
            "WHERE guild_id = ? AND user_id = ? AND log_date = ?",
            (str(guild_id), str(user_id), today),
        ).fetchone()
    return row[0] if row else 0


def get_grand_total(guild_id: int, user_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT total FROM participants WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return row[0] if row else 0


# ---------- inactivity / nagging ----------

def get_last_active_date(guild_id: int, user_id: int, joined_date: str) -> str:
    """Most recent log date, or the join date if they've never logged."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(log_date) FROM daily_logs "
            "WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return row[0] if row and row[0] else joined_date


def list_participants(guild_id: int):
    """Returns [(user_id, joined_date, last_nagged_date, timezone), ...] for a guild."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT user_id, joined_date, last_nagged_date, timezone "
            "FROM participants WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchall()
    return rows


def list_participant_stats(guild_id: int):
    """Returns [(user_id, joined_date, total, timezone), ...] for a guild,
    ordered by lifetime total descending -- for the scoreboard."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT user_id, joined_date, total, timezone "
            "FROM participants WHERE guild_id = ? ORDER BY total DESC",
            (str(guild_id),),
        ).fetchall()
    return rows


def list_guild_ids():
    with _connect() as conn:
        rows = conn.execute("SELECT guild_id FROM guilds").fetchall()
    return [r[0] for r in rows]


def record_nag(guild_id: int, user_id: int, nag_date: str):
    with _connect() as conn:
        conn.execute(
            "UPDATE participants SET last_nagged_date = ? "
            "WHERE guild_id = ? AND user_id = ?",
            (nag_date, str(guild_id), str(user_id)),
        )
