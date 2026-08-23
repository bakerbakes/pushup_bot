"""
pushup_bot

A 100-day push-up challenge bot with a single, bot-wide lifespan.

Commands:
  /pushupjoin              - opt in to the challenge (optional timezone)
  /pushuplog <count>       - log a set of push-ups done just now
  /pushuptoday             - see today's logged count
  /pushuptotal             - see your lifetime total + what day of 100 it is
  /pushupscoreboard        - see everyone's lifetime total and daily average
  /pushuptimezone          - set/update your timezone
  /pushupsetchannel        - (admin) pick the inactivity check-in channel

The 100-day countdown is global (not per-server): day 1 starts 24
hours after the bot's first-ever deploy, and on day 100 the bot
announces its own end and goes quiet everywhere it's running.
"""

import os
import logging
import sqlite3
from datetime import date

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()  # must run before importing db/messages -- both read env vars at import time

logging.basicConfig(level=logging.INFO)  # must also run first -- both modules log at import time
log = logging.getLogger("pushup_bot")

import db
import messages

INACTIVITY_THRESHOLD_DAYS = 5

TIMEZONE_CHOICES = [
    app_commands.Choice(name="Eastern (EST/EDT)", value="America/New_York"),
    app_commands.Choice(name="Central (CST/CDT)", value="America/Chicago"),
    app_commands.Choice(name="Mountain (MST/MDT)", value="America/Denver"),
    app_commands.Choice(name="Pacific (PST/PDT)", value="America/Los_Angeles"),
]

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()


class PushupBot(commands.Bot):
    """discord.py never dispatches an 'on_close' event, so cleanup on
    shutdown has to happen by overriding close() itself."""

    async def close(self):
        if self.http_session is not None:
            await self.http_session.close()
        await super().close()


bot = PushupBot(command_prefix="!", intents=intents)
bot.http_session = None  # aiohttp.ClientSession, created in on_ready


async def not_destructed(interaction: discord.Interaction) -> bool:
    """Global gate: once the 100-day lifespan is over, the bot goes inert."""
    return not db.is_destructed()


@bot.event
async def on_ready():
    db.init_db()
    # Ensures every guild the bot is currently in has a row (needed for
    # reminder-channel storage) in case it was already in a guild before
    # this run, or the DB was reset.
    for guild in bot.guilds:
        db.set_guild_start_if_missing(guild.id)

    if bot.http_session is None:
        bot.http_session = aiohttp.ClientSession()

    try:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        log.exception(f"Slash command sync failed: {e}")

    if not check_inactivity.is_running():
        check_inactivity.start()
    if not check_self_destruct.is_running():
        check_self_destruct.start()

    log.info(f"pushup_bot is online as {bot.user}.")


@bot.event
async def on_guild_join(guild: discord.Guild):
    db.set_guild_start_if_missing(guild.id)
    log.info(f"Joined guild {guild.name} ({guild.id}).")


@bot.tree.command(name="pushupjoin", description="Join the 100-day push-up challenge")
@app_commands.describe(
    timezone="Your local timezone, so your daily reset lines up with your day (defaults to UTC)"
)
@app_commands.choices(timezone=TIMEZONE_CHOICES)
@app_commands.check(not_destructed)
async def pushupjoin(
    interaction: discord.Interaction, timezone: app_commands.Choice[str] = None
):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This challenge is server-based -- run this in a server, not a DM.",
            ephemeral=True,
        )
        return

    tz = timezone.value if timezone else "UTC"
    is_new = db.join_user(interaction.guild_id, interaction.user.id, tz)
    day_number = db.get_day_number()
    # First person to join in a server sets the default check-in channel,
    # unless an admin has already picked one with /pushupsetchannel.
    db.set_reminder_channel_if_missing(interaction.guild_id, interaction.channel_id)

    day_status = (
        "The challenge kicks off within the next 24 hours."
        if day_number == 0
        else f"We're on **day {day_number} of 100**."
    )

    if not is_new:
        await interaction.response.send_message(
            f"You're already signed up, champ. {day_status} "
            f"Get after it with `/pushuplog`.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"{messages.join_message()}\n\n"
        f"{day_status} Log sets anytime with `/pushuplog`."
    )


@bot.tree.command(
    name="pushuptimezone", description="Set or update your timezone for daily reset boundaries"
)
@app_commands.describe(timezone="Your local timezone")
@app_commands.choices(timezone=TIMEZONE_CHOICES)
@app_commands.check(not_destructed)
async def pushuptimezone(
    interaction: discord.Interaction, timezone: app_commands.Choice[str]
):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This challenge is server-based -- run this in a server, not a DM.",
            ephemeral=True,
        )
        return

    updated = db.set_user_timezone(interaction.guild_id, interaction.user.id, timezone.value)
    if not updated:
        await interaction.response.send_message(
            "You haven't joined the challenge yet. Run `/pushupjoin` first.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"Timezone set to **{timezone.name}**. Your daily reset now lines up with that zone.",
        ephemeral=True,
    )


@bot.tree.command(name="pushuplog", description="Log a set of push-ups you just did")
@app_commands.describe(count="How many push-ups in this set")
@app_commands.check(not_destructed)
async def pushuplog(interaction: discord.Interaction, count: int):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This challenge is server-based -- run this in a server, not a DM.",
            ephemeral=True,
        )
        return

    if count <= 0:
        await interaction.response.send_message(
            "Nice try. Give me a real number greater than 0.", ephemeral=True
        )
        return

    if count > 500:
        await interaction.response.send_message(
            "500+ push-ups in one set? Respect the claim, but double-check that number "
            "and log again.",
            ephemeral=True,
        )
        return

    if not db.is_joined(interaction.guild_id, interaction.user.id):
        db.join_user(interaction.guild_id, interaction.user.id)

    previous_total = db.get_grand_total(interaction.guild_id, interaction.user.id)
    result = db.add_pushups(interaction.guild_id, interaction.user.id, count)
    milestone = messages.total_milestone_message(previous_total, result["grand_total"])

    if result["crossed_goal_today"]:
        text = (
            f"{messages.daily_goal_message()}\n\n"
            f"Today: **{result['today_total']}** push-ups | "
            f"Lifetime total: **{result['grand_total']}** | "
            f"Day {result['day_number']} of 100"
        )
        if milestone:
            text += f"\n\n{milestone}"
        gif = await messages.random_gif(bot.http_session)
        await interaction.response.send_message(f"{text}\n{gif}")
        return

    text = (
        f"{messages.log_ack_message()} "
        f"(+{count} -- today: {result['today_total']}/100, "
        f"lifetime: {result['grand_total']})"
    )
    if milestone:
        text += f"\n\n{milestone}"

    await interaction.response.send_message(text)


@bot.tree.command(name="pushuptoday", description="Check your push-up count for today")
@app_commands.check(not_destructed)
async def pushuptoday(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This challenge is server-based -- run this in a server, not a DM.",
            ephemeral=True,
        )
        return

    if not db.is_joined(interaction.guild_id, interaction.user.id):
        await interaction.response.send_message(
            "You haven't joined the challenge yet. Run `/pushupjoin` first.",
            ephemeral=True,
        )
        return

    today_total = db.get_today_total(interaction.guild_id, interaction.user.id)
    if today_total >= 100:
        msg = f"You're at **{today_total}/100** today. Goal already hit -- nice work."
    elif today_total == 0:
        msg = "You haven't logged anything today. Get after it with `/pushuplog`."
    else:
        remaining = 100 - today_total
        msg = f"You're at **{today_total}/100** today. {remaining} to go."

    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(
    name="pushuptotal",
    description="Check your lifetime push-up total for this challenge",
)
@app_commands.check(not_destructed)
async def pushuptotal(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This challenge is server-based -- run this in a server, not a DM.",
            ephemeral=True,
        )
        return

    if not db.is_joined(interaction.guild_id, interaction.user.id):
        await interaction.response.send_message(
            "You haven't joined the challenge yet. Run `/pushupjoin` first.",
            ephemeral=True,
        )
        return

    total = db.get_grand_total(interaction.guild_id, interaction.user.id)
    day_number = db.get_day_number()
    days_remaining = db.get_days_remaining()

    if day_number == 0:
        status = "The challenge hasn't started yet -- kicks off within 24 hours of deploy."
    elif day_number > 100:
        status = "The 100-day challenge window has ended -- final tally below."
    else:
        status = f"Day {day_number} of 100 ({days_remaining} day(s) left)."

    await interaction.response.send_message(
        f"Lifetime total: **{total}** push-ups.\n{status}",
        ephemeral=True,
    )


@bot.tree.command(
    name="pushupscoreboard",
    description="See everyone's lifetime total and daily average",
)
@app_commands.check(not_destructed)
async def pushupscoreboard(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This challenge is server-based -- run this in a server, not a DM.",
            ephemeral=True,
        )
        return

    stats = db.list_participant_stats(interaction.guild_id)
    if not stats:
        await interaction.response.send_message(
            "Nobody's joined yet. Be the first with `/pushupjoin`.", ephemeral=True
        )
        return

    lines = []
    for rank, (user_id_str, joined_date, total, tz) in enumerate(stats, start=1):
        days_in = (db.local_today(tz) - date.fromisoformat(joined_date)).days + 1
        avg = total / max(1, days_in)
        lines.append(
            f"**{rank}.** <@{int(user_id_str)}> -- **{total}** lifetime | {avg:.1f}/day avg"
        )

    header = "**Push-up Scoreboard**\n"
    text = header + "\n".join(lines)

    if len(text) > 1900:
        trimmed = []
        running_len = len(header)
        for line in lines:
            if running_len + len(line) + 1 > 1900:
                trimmed.append(f"_...and {len(stats) - len(trimmed)} more._")
                break
            trimmed.append(line)
            running_len += len(line) + 1
        text = header + "\n".join(trimmed)

    await interaction.response.send_message(text)


@bot.tree.command(
    name="pushupsetchannel",
    description="Set which channel gets the 'you ok bro' inactivity check-ins",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def pushupsetchannel(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This challenge is server-based -- run this in a server, not a DM.",
            ephemeral=True,
        )
        return

    db.set_reminder_channel(interaction.guild_id, interaction.channel_id)
    await interaction.response.send_message(
        f"Got it. Inactivity check-ins will be posted in {interaction.channel.mention}."
    )


@pushupsetchannel.error
async def pushupsetchannel_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the 'Manage Server' permission to set this.", ephemeral=True
        )
    else:
        raise error


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    """
    Global fallback. Skips errors a command's own handler already dealt
    with (discord.py calls both), replies with the destroyed-challenge
    message for the not_destructed gate, gives a friendlier message for
    a DB hiccup, and otherwise tells the user to try again instead of
    leaving Discord's unhelpful "The application did not respond".
    """
    if isinstance(error, app_commands.MissingPermissions):
        return  # already handled by pushupsetchannel's own error handler

    if isinstance(error, app_commands.CheckFailure):
        msg = messages.destroyed_reply_message()
    else:
        original = getattr(error, "original", error)
        if isinstance(original, sqlite3.OperationalError):
            log.error(f"Database error on command: {original}")
            msg = (
                "Hit a temporary storage hiccup logging that -- nothing lost, "
                "just try the command again in a moment."
            )
        else:
            log.exception(f"Unhandled app command error: {error}")
            msg = "Something went wrong running that command. Try again in a moment."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass  # interaction already expired, nothing more we can do


@tasks.loop(hours=24)
async def check_inactivity():
    """
    Once a day, scan every guild's participants. Anyone who hasn't
    logged push-ups in 5+ days (counted in their own local timezone)
    gets a public nudge in the guild's reminder channel. Re-nags every
    additional 5 days of silence rather than every single day.
    """
    if db.is_destructed():
        return  # challenge is over, no more nagging

    for guild_id_str in db.list_guild_ids():
        guild_id = int(guild_id_str)
        try:
            await _nag_inactive_in_guild(guild_id)
        except Exception:
            # A single guild misbehaving (bad data, an unexpected discord.py
            # error, etc.) must never take the whole daily loop down for the
            # rest of the bot's run -- discord.ext.tasks does not auto-retry
            # after an unhandled exception.
            log.exception(f"check_inactivity failed for guild {guild_id}")


async def _nag_inactive_in_guild(guild_id: int):
    channel_id = db.get_reminder_channel(guild_id)
    if not channel_id:
        return  # nobody has joined / no channel set yet

    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except discord.HTTPException:
            return

    for user_id_str, joined_date, last_nagged_date, tz in db.list_participants(guild_id):
        try:
            user_id = int(user_id_str)
            today = db.local_today(tz)
            last_active = date.fromisoformat(
                db.get_last_active_date(guild_id, user_id, joined_date)
            )
            days_inactive = (today - last_active).days

            if days_inactive < INACTIVITY_THRESHOLD_DAYS:
                continue
            if days_inactive % INACTIVITY_THRESHOLD_DAYS != 0:
                continue  # only nag on 5, 10, 15... day marks
            if last_nagged_date == today.isoformat():
                continue  # already nagged today (e.g. after a restart)

            try:
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            except discord.HTTPException:
                continue

            try:
                await channel.send(
                    messages.inactivity_nag_message(member.mention, days_inactive)
                )
            except discord.HTTPException as e:
                log.warning(f"Failed to send nag in guild {guild_id}: {e}")
                continue

            db.record_nag(guild_id, user_id, today.isoformat())
        except Exception:
            log.exception(f"check_inactivity failed for user {user_id_str} in guild {guild_id}")


@check_inactivity.before_loop
async def before_check_inactivity():
    await bot.wait_until_ready()


def _pick_announce_channel(guild: discord.Guild):
    """Reminder channel if set, otherwise the first channel the bot can
    actually send a message in."""
    channel_id = db.get_reminder_channel(guild.id)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel is not None:
            return channel
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            return channel
    return None


@tasks.loop(hours=1)
async def check_self_destruct():
    """Once the bot's single 100-day lifespan is up, announce it once in
    every guild and go permanently inert (see not_destructed check)."""
    if db.is_destructed():
        return
    if db.get_day_number() <= db.CHALLENGE_LENGTH_DAYS:
        return

    db.mark_destructed()
    log.info("Day 100 reached -- triggering self-destruct sequence.")

    gif = await messages.random_explosion_gif(bot.http_session)
    text = f"{messages.self_destruct_message()}\n{gif}"

    for guild in bot.guilds:
        try:
            channel = _pick_announce_channel(guild)
            if channel is None:
                continue
            await channel.send(text)
        except Exception:
            # mark_destructed() has already committed -- this is a one-shot
            # announcement, so one bad guild must not stop the rest from
            # getting it (and must not take the whole loop down either).
            log.exception(f"Failed to post self-destruct message in guild {guild.id}")


@check_self_destruct.before_loop
async def before_check_self_destruct():
    await bot.wait_until_ready()


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in."
        )
    bot.run(TOKEN)
