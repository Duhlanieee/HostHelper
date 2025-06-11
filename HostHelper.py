import discord
from discord.ext import commands
import re
from datetime import datetime
from collections import defaultdict
import time
import asyncio


# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True
intents.presences = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

SERVER_ID = REDACTED  # Your server ID
AUTHOR_ID = REDACTED # Admin user ID
EVENTS_CHANNEL_ID = REDACTED  # Events channel ID
LOG_CHANNEL_ID = REDACTED # Log channel ID for logging bot activities

current_custom_status = "under construction"
reaction_cooldowns = defaultdict(float)
event_threads = {}
deactivated_messages = set()

log = None  # Placeholder for our logger


async def setup_log_channel():
    global log
    guild = None
    while guild is None:
        guild = bot.get_guild(SERVER_ID)
        if guild is None:
            await asyncio.sleep(1)
    status_logs_channel = guild.get_channel(LOG_CHANNEL_ID)

    class LogWrapper:
        def __init__(self, channel):
            self.channel = channel

        async def send(self, message):
            if self.channel:
                try:
                    await self.channel.send(message)
                except Exception:
                    pass

    log = LogWrapper(status_logs_channel)
    globals()['log'] = log






def parse_event_info(message_content):
    lines = message_content.splitlines()
    if len(lines) < 2:
        return None, None, None

    date_line = lines[0].strip()
    date_line_clean = re.sub(r'^[^\w]*', '', date_line).strip(", ")

    date_match = re.search(
        r'(?P<month>January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+'
        r'(?P<day>\d{1,2})(?:st|nd|rd|th)?',
        date_line_clean,
        re.IGNORECASE
    )

    if not date_match:
        if log:
            asyncio.create_task(log.send(f"⚠️ Failed to parse date from: {date_line_clean}"))
        return None, None, None

    month = date_match.group("month")
    day = date_match.group("day")
    suffix_match = re.search(r'\d{1,2}(st|nd|rd|th)', date_line_clean)
    suffix = suffix_match.group(1) if suffix_match else "th"

    event_date = f"{month} {day}{suffix}"
    channel_date_part = f"{month.lower()}-{day}{suffix}"

    known_events = ["Wii Cook", "Wii Go Out To Eat"]
    line2 = lines[1].strip()

    event_name = None
    for base in known_events:
        if re.search(rf'\b{re.escape(base)}\b', line2, re.IGNORECASE):
            event_name = base
            break

    if not event_name:
        if log:
            asyncio.create_task(log.send(f"⚠️ Line2 '{line2}' didn't match any known event names."))
        return None, None, None

    base_event_hyphenated = re.sub(r'\W+', '-', event_name.lower()).strip('-')
    channel_name = f"{base_event_hyphenated}-{channel_date_part}"

    return event_name, channel_name, event_date


async def create_event_thread(message, event_name):
    existing_threads = [t for t in message.channel.threads if t.name == f"{event_name} Thread"]
    if existing_threads:
        return existing_threads[0]
    thread = await message.create_thread(name=f"{event_name} Thread", auto_archive_duration=10080)
    await thread.send("This is a thread for attendance notices.")
    await thread.edit(locked=True, archived=False)
    return thread




@bot.event
async def on_ready():
    await setup_log_channel()
    await log.send(f"Logged in as {bot.user}")
    await bot.change_presence(status=discord.Status.online, activity=discord.CustomActivity(name=current_custom_status))
    await log.send(f"Status set to **{current_custom_status}**")

    guild = bot.get_guild(SERVER_ID)
    if not guild:
        await log.send("Guild not found!")
        return

    events_channel = discord.utils.get(guild.text_channels, id=EVENTS_CHANNEL_ID)
    events_category = discord.utils.get(guild.categories, name='Events')

    if not events_channel or not events_category:
        await log.send("One or more required channels/categories are missing.")
        return

    private_channels = {channel.name: channel for channel in events_category.text_channels}

    debug_lines = []
    debug_lines.append(f"Found {len(private_channels)} private channels in Events category:")
    for name in private_channels.keys():
        debug_lines.append(f"{name}")

    messages = [msg async for msg in events_channel.history(limit=4)]

    recovered = 0
    skipped_author = 0
    skipped_parse = 0
    skipped_missing_channel = 0

    for msg in messages:
        if msg.author.id != AUTHOR_ID:
            debug_lines.append(f"  Skipped due to author mismatch: {msg.author.id}")
            skipped_author += 1
            continue

        try:
            event_name, channel_name, event_date = parse_event_info(msg.content)
            # debug_lines.append(f"  Parsed channel_name: {channel_name}")
        except Exception as e:
            debug_lines.append(f"  Failed to parse event info for message {msg.id}: {e}")
            skipped_parse += 1
            continue

        if not event_name or not channel_name:
            debug_lines.append(f"  Parsed data incomplete: event_name or channel_name is None")
            skipped_missing_channel += 1
            continue

        private_channel = private_channels.get(channel_name)
        if not private_channel:
            # debug_lines.append(f"  No matching private channel found for: '{channel_name}'")
            skipped_missing_channel += 1
            continue

        thread = await create_event_thread(msg, event_name)
        event_threads[msg.id] = (thread, private_channel)
        recovered += 1
        # debug_lines.append(f"  Recovered event thread for message ID {msg.id}")
        
        try:
            await events_channel.fetch_message(msg.id)
        except Exception as e:
            await log.send(f"Failed to fetch/cache message {msg.id}: {e}")

    try:
        await log.send("\n".join(debug_lines))
    except Exception as e:
        await log.send(f"Failed to send debug logs: {e}")
    await bot.get_channel(EVENTS_CHANNEL_ID).fetch_message(msg.id)  # Force cache

    # Manually add reaction to ensure it's there
    try:
        await msg.add_reaction("👍")
    except discord.errors.Forbidden:
        await log.send("❌ Bot missing permission to add reactions.")

    summary = (
        f"✅ Startup Summary\n"
        f"- Recovered threads: **{recovered}**\n"
        f"- Skipped (parse error): **{skipped_parse}**\n"
        f"- Skipped (no channel match): **{skipped_missing_channel}**\n"
        f"- Total messages scanned: **{len(messages)}**"
    )
    await log.send(summary)






@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.channel.id != EVENTS_CHANNEL_ID or message.author == bot.user:
        return

    event_name, channel_name, event_date = parse_event_info(message.content)
    if not (event_name and event_date):
        return

    await message.add_reaction("\U0001F44D")

    if message.id in event_threads:
        if log:
            await log.send(f"Skipping duplicate event setup for message ID {message.id}")
        return

    event_thread = await message.create_thread(name=f"{event_name} Thread", auto_archive_duration=10080)
    await event_thread.send("This is a thread for attendance notices.")
    await event_thread.edit(locked=True, archived=False)

    guild = bot.get_guild(SERVER_ID)
    category = discord.utils.get(guild.categories, name="Events")
    if category is None:
        category = await guild.create_category("Events")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True),
    }

    private_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
    await private_channel.send(f"This is the chat for those attending {event_name} on {event_date}!")

    event_threads[message.id] = (event_thread, private_channel)


@bot.event
async def on_reaction_add(reaction, user):
    await bot.wait_until_ready()
    await log.send(f"Detected a reaction: {reaction.emoji} by {user.name}")

    if user.bot:
        await log.send(f"wrong user")
        return
    if not reaction.message.guild or reaction.message.guild.id != SERVER_ID:
        await log.send(f"wrong server")
        return
    if reaction.message.channel.id != EVENTS_CHANNEL_ID or user == bot.user:
        await log.send(f"wrong channel")
        return

    try:
        await log.send(f"🟢 Reaction ADD detected by {user.name} on msg {reaction.message.id} with emoji {reaction.emoji}")

        if reaction.message.id in deactivated_messages:
            await log.send(f"⚠️ Reaction ignored — message {reaction.message.id} is deactivated.")
            return

        if str(reaction.emoji) != "\U0001F44D":
            await log.send(f"⚠️ Reaction ignored — emoji {reaction.emoji} not recognized.")
            return

        now = time.time()
        if now - reaction_cooldowns[user.id] < 20:
            await log.send(f"⚠️ Reaction ignored — cooldown active for {user.name}")
            return
        reaction_cooldowns[user.id] = now
        
        if reaction.message.id not in event_threads:
            await log.send(f"⚠️ Reaction ignored — message ID {reaction.message.id} not tracked as event")
            return


        guild = bot.get_guild(SERVER_ID)
        member = guild.get_member(user.id) or await guild.fetch_member(user.id)
        await log.send(f"Member object retrieved: {member}")
        display_name = member.nick if member and member.nick else user.name

        event_name, channel_name, event_date = parse_event_info(reaction.message.content)
        if not event_name:
            await log.send(f"❌ Reaction failed — could not parse event info for msg {reaction.message.id}")
            return

        private_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if private_channel:
            await private_channel.set_permissions(member or user, view_channel=True, send_messages=True)
            await private_channel.send(f"{display_name} is attending this event!")
            await log.send(f"✅ Access granted to {display_name} for channel {channel_name}")

        thread = event_threads.get(reaction.message.id)
        if thread:
            await thread[0].send(f"{display_name} is attending this event!")
            await log.send(f"📌 Attendance noted for {display_name} in thread")

    except Exception as e:
        await log.send(f"🔥 ERROR in on_reaction_add: {e}")


@bot.event
async def on_reaction_remove(reaction, user):
    await bot.wait_until_ready()

    if user.bot:
        return
    if not reaction.message.guild or reaction.message.guild.id != SERVER_ID:
        return
    if reaction.message.channel.id != EVENTS_CHANNEL_ID or user == bot.user:
        return

    try:
        await log.send(f"🔴 Reaction REMOVE detected by {user.name} on msg {reaction.message.id} with emoji {reaction.emoji}")

        if reaction.message.id in deactivated_messages:
            await log.send(f"⚠️ Reaction remove ignored — message {reaction.message.id} is deactivated.")
            return

        if str(reaction.emoji) != "\U0001F44D":
            await log.send(f"⚠️ Reaction remove ignored — emoji {reaction.emoji} not recognized.")
            return
        
        now = time.time()
        if now - reaction_cooldowns[user.id] < 20:
            await log.send(f"⚠️ Reaction ignored — cooldown active for {user.name}")
            return
        reaction_cooldowns[user.id] = now
        
        if reaction.message.id not in event_threads:
            await log.send(f"⚠️ Reaction ignored — message ID {reaction.message.id} not tracked as event")
            return

        guild = bot.get_guild(SERVER_ID)
        member = guild.get_member(user.id) or await guild.fetch_member(user.id)
        await log.send(f"Member object retrieved: {member}")
        display_name = member.nick if member and member.nick else user.name

        event_name, channel_name, event_date = parse_event_info(reaction.message.content)
        if not event_name:
            await log.send(f"❌ Reaction remove failed — could not parse event info for msg {reaction.message.id}")
            return

        private_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if private_channel:
            await private_channel.set_permissions(member or user, overwrite=None)
            await private_channel.send(f"{display_name} is no longer attending this event.")
            await log.send(f"✅ Access revoked for {display_name} from channel {channel_name}")

        thread = event_threads.get(reaction.message.id)
        if thread:
            await thread[0].send(f"{display_name} is no longer attending this event.")
            await log.send(f"📌 Cancellation noted for {display_name} in thread")

    except Exception as e:
        await log.send(f"🔥 ERROR in on_reaction_remove: {e}")





@bot.event
async def on_guild_channel_delete(channel):
    if not isinstance(channel, discord.TextChannel):
        return

    if getattr(channel.category, "name", "").lower() == "events":
        for message_id, (thread, private_channel) in list(event_threads.items()):
            if private_channel.id == channel.id:
                event_threads.pop(message_id)
                if log:
                    try:
                        await log.send(f"⚠️ Event channel '{channel.name}' deleted. Removed message ID {message_id} from event_threads.")
                    except Exception as e:
                        print(f"Logging failed: {e}")



@bot.command()
async def dnd(ctx):
    if ctx.author.id != AUTHOR_ID:
        await ctx.send("You don't have permission to do that.")
        return
    await bot.change_presence(activity=discord.CustomActivity(name=current_custom_status), status=discord.Status.dnd)
    await ctx.send("Status set to **Do Not Disturb**")

@bot.command()
async def on(ctx):
    if ctx.author.id != AUTHOR_ID:
        await ctx.send("You don't have permission to do that.")
        return
    await bot.change_presence(status=discord.Status.online)
    await ctx.send("Status set to **Online**")

@bot.command()
async def status(ctx, *, new_status: str):
    global current_custom_status
    if ctx.author.id != AUTHOR_ID:
        await ctx.send("You don't have permission to do that.")
        return
    current_custom_status = new_status  # Save it globally
    try:
        # Keep current presence (DND/Online), only change activity
        current_presence = discord.Status.online  # fallback
        guild = bot.get_guild(SERVER_ID)
        if guild:
            me = guild.me
            if me:
                current_presence = me.status
        await bot.change_presence(activity=discord.CustomActivity(name=new_status), status=current_presence)
        await ctx.send(f"Custom status set to **{new_status}**")
    except Exception as e:
        await ctx.send(f"Failed to set custom status: {e}")


# Run the bot with your token
bot.run("REDACTED")

