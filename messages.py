"""
Message pools for pushup_bot.

Everything is picked with random.choice() at call time so a 100-day
run doesn't feel like the same three lines on repeat. Add more lines
to any list at any time -- nothing else needs to change.
"""

import os
import random
import logging

import aiohttp

log = logging.getLogger("pushup_bot")

GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
GIPHY_SEARCH_URL = "https://api.giphy.com/v1/gifs/random"

if GIPHY_API_KEY:
    log.info("GIPHY_API_KEY found -- live gifs enabled.")
else:
    log.warning(
        "GIPHY_API_KEY not set -- always using the static gif fallback lists. "
        "If you expected a key to be picked up, check it's actually reaching "
        "the process before this module is imported (e.g. a .env file needs "
        "load_dotenv() to run first)."
    )

# Shown when a user runs /pushupjoin
JOIN_MESSAGES = [
    "Look at you, already built like a house. Signing you up now -- 100 push-ups a day, 100 days. Let's go.",
    "Honestly? You look strong enough to skip this challenge. But you're in now, so let's make it official.",
    "You've got main-character energy and a main-character physique. Welcome to the 100-day push-up club.",
    "Rare to see someone this photogenic AND this ready to grind. You're signed up.",
    "You didn't need to convince me you're strong, the arms already did that. Enrollment confirmed.",
    "Confidence, good looks, and now a push-up habit. You're basically unstoppable. Welcome in.",
    "You in? You're in. And for the record, you were already looking dangerously fit before this.",
    "Say less. You clearly already lift something heavy for a living. Sign-up complete.",
    "The gym rats wish they looked like you on day zero. Let's turn that into day 100.",
    "Welcome aboard, champ. You walked in looking like you bench the equipment rack for fun.",
    "Signed up. Also, has anyone told you that you have great posture for someone about to do this many push-ups?",
    "You're in the challenge now. Try not to intimidate the rest of the server with those guns.",
]

# Short acknowledgment after logging a set that does NOT hit the daily goal
LOG_ACK_MESSAGES = [
    "Logged. Keep stacking those reps.",
    "Noted. That's more than most people did today.",
    "Got it -- added to the tally.",
    "Solid set. On the board.",
    "Counted. Your future self says thanks.",
    "Locked in. Keep the momentum going.",
    "Added. Every rep counts toward the 100.",
    "Recorded. You're chipping away at it.",
    "That's in the books. Onward.",
    "Nice, tracked. Keep going when you're ready.",
    "Set logged. Small steps, real progress.",
    "In the ledger. Come back for more whenever.",
]

# Sent the moment a user crosses 100 push-ups for the day
DAILY_GOAL_MESSAGES = [
    "**100 down for the day.** That's the goal, right there. Go put your feet up.",
    "**Triple digits.** Today's push-up quota: absolutely demolished.",
    "**100/100.** You just out-worked most of the internet today.",
    "That's the century mark. **Goal hit.** Go be smug about it, you earned it.",
    "**Daily goal: complete.** Somewhere, a gym bro is nodding in approval.",
    "100 push-ups, done and dusted. Rest easy, warrior.",
    "You just hit triple digits. **The floor fears you now.**",
    "**Goal crushed.** That's a full 100 for today -- take the win.",
    "Boom. 100 push-ups logged. Go flex on somebody.",
    "That's it, that's the day. **100 push-ups, in the bag.**",
]

# Fallback/extra flavor lines to occasionally append to a daily goal message
GOAL_FLAVOR_ADDENDA = [
    "Tomorrow the countdown keeps moving -- see you then.",
    "The couch has never looked so earned.",
    "Somewhere your future self is doing a victory lap.",
    "That's one more day closer to the finish line.",
    "Hydrate. You've earned it.",
]

# Milestones on the running GRAND total (across the whole 100-day run)
TOTAL_MILESTONE_MESSAGES = {
    500: "**500 lifetime push-ups.** You're not just participating, you're putting in work.",
    1000: "**1,000 push-ups total.** Four digits. Certified grinder status.",
    2500: "**2,500 push-ups.** At this point you should have your own gravitational pull.",
    5000: "**5,000 push-ups lifetime.** That's not a hobby anymore, that's a lifestyle.",
    10000: "**10,000 push-ups.** Frankly, we're a little scared of you now. Incredible work.",
}

# Sent once, server-wide, the moment the bot's 100-day lifespan ends
SELF_DESTRUCT_MESSAGES = [
    "**Day 100.** That's the whole run. It's been real -- self-destructing now. 💥",
    "100 days, countless push-ups, one bot. Mission complete. Going out with a bang. 💥",
    "The countdown's over. Thanks for the reps -- this is me signing off, loudly. 💥",
    "**That's a wrap.** 100 days down. Initiating self-destruct. It's been an honor.",
    "Day 100 achieved. No more nagging, no more logging -- just this. Goodbye. 💥",
]

# Shown (ephemerally) if someone tries a command after self-destruct
DESTROYED_REPLY_MESSAGES = [
    "This challenge ended on day 100. The bot's gone quiet -- GG.",
    "100 days are up. Nothing left running on this end. Thanks for playing.",
    "The push-up challenge is over. This bot won't be logging anything else.",
    "Day 100 came and went. This is just an echo now -- no logs, no commands.",
]

# Sent as a public check-in when someone's gone quiet for 5+ days
INACTIVITY_NAG_MESSAGES = [
    "{mention} you ok bro? Haven't seen a push-up out of you in {days} days.",
    "{mention} bro... {days} days of silence. Everything good?",
    "{mention} the floor misses you. {days} days since your last set.",
    "{mention} checking in -- {days} days without a log. You still with us?",
    "{mention} {days} days of radio silence. No judgment, just checking you're alive.",
    "{mention} it's been {days} days. Whenever you're ready, `/pushuplog` is right there.",
    "{mention} you good? {days} days since your last push-up.",
]


def inactivity_nag_message(mention: str, days: int) -> str:
    return random.choice(INACTIVITY_NAG_MESSAGES).format(mention=mention, days=days)


def self_destruct_message() -> str:
    return random.choice(SELF_DESTRUCT_MESSAGES)


def destroyed_reply_message() -> str:
    return random.choice(DESTROYED_REPLY_MESSAGES)


# Static fallback gifs -- used if no GIPHY_API_KEY is set, or if a
# live lookup fails for any reason (network hiccup, rate limit, etc).
# NOTE: verify these still resolve; hosted gif links can go stale.
GIFS = [
    "https://media.giphy.com/media/l0HlNaQ6gWfllcjDO/giphy.gif",
    "https://media.giphy.com/media/xT9IgG50Fb7Mi0prBC/giphy.gif",
    "https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif",
    "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
    "https://media.giphy.com/media/l46Cy1rHbQ92uuLXa/giphy.gif",
]

# Search terms used when pulling a live gif from GIPHY. One is picked
# at random each time, so the theme varies along with the specific gif.
GIPHY_SEARCH_TAGS = [
    "arnold schwarzenegger flex",
    "rocky training montage",
    "gym motivation",
    "workout beast mode",
    "flexing muscles",
    "you got this gym",
    "strong man victory",
    "push ups gif",
]

# Static fallback gifs for the day-100 self-destruct announcement, used
# only if no GIPHY_API_KEY is set or a live lookup fails. Both entries
# were fetched and visually verified -- see GIFS above for the caveat
# about hosted links going stale over time.
EXPLOSION_GIFS = [
    "https://media.giphy.com/media/oe33xf3B50fsc/giphy.gif",
    "https://media.giphy.com/media/l3q2yNnyrsh9AMAaA/giphy.gif",
]

GIPHY_EXPLOSION_SEARCH_TAGS = [
    "explosion",
    "self destruct",
    "mission impossible explosion",
    "boom explosion",
]


def join_message() -> str:
    return random.choice(JOIN_MESSAGES)


def log_ack_message() -> str:
    return random.choice(LOG_ACK_MESSAGES)


def daily_goal_message() -> str:
    msg = random.choice(DAILY_GOAL_MESSAGES)
    if random.random() < 0.5:
        msg += "\n" + random.choice(GOAL_FLAVOR_ADDENDA)
    return msg


def total_milestone_message(previous_total: int, new_total: int) -> str | None:
    """Returns a milestone message if new_total just crossed a threshold."""
    for threshold, msg in sorted(TOTAL_MILESTONE_MESSAGES.items()):
        if previous_total < threshold <= new_total:
            return msg
    return None


async def _fetch_giphy_gif(
    session: aiohttp.ClientSession, search_tags: list[str]
) -> str | None:
    """Tries a live GIPHY lookup. Returns None on any failure so the
    caller can fall back to the static list -- a bad gif call should
    never break the actual push-up logging."""
    if not GIPHY_API_KEY:
        return None

    params = {
        "api_key": GIPHY_API_KEY,
        "tag": random.choice(search_tags),
        "rating": "pg-13",
    }
    try:
        async with session.get(
            GIPHY_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            if resp.status != 200:
                log.warning(f"GIPHY lookup returned status {resp.status}")
                return None
            data = await resp.json()
            url = (
                data.get("data", {})
                .get("images", {})
                .get("original", {})
                .get("url")
            )
            return url or None
    except (aiohttp.ClientError, TimeoutError) as e:
        log.warning(f"GIPHY lookup failed, using fallback gif: {e}")
        return None


async def random_gif(session: aiohttp.ClientSession | None = None) -> str:
    """
    Returns a gif URL. If a GIPHY_API_KEY is configured and session
    is provided, tries a live random gif first; otherwise (or on any
    failure) falls back to the static GIFS list.
    """
    if session is not None:
        live = await _fetch_giphy_gif(session, GIPHY_SEARCH_TAGS)
        if live:
            return live
    return random.choice(GIFS)


async def random_explosion_gif(session: aiohttp.ClientSession | None = None) -> str:
    """Same idea as random_gif(), but themed for the day-100 self-destruct."""
    if session is not None:
        live = await _fetch_giphy_gif(session, GIPHY_EXPLOSION_SEARCH_TAGS)
        if live:
            return live
    return random.choice(EXPLOSION_GIFS)
