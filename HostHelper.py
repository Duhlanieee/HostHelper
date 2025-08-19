import discord
from discord.ext import commands
import re
from datetime import datetime
from collections import defaultdict
import time
import asyncio
import json
import os
import unicodedata
from operator import itemgetter
from discord.ext import tasks
from datetime import datetime, time as dt_time, timedelta
import time
from zoneinfo import ZoneInfo

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True
intents.presences = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

SERVER_ID = REDACTED  # Server ID (obviously lmao)
AUTHOR_ID = REDACTED # Admin user ID (das me!)
EVENTS_CHANNEL_ID = REDACTED  # Events channel ID
EVENTS_CATEGORY_ID = REDACTED # Events category (where all the private event chats go)
LOG_CHANNEL_ID = REDACTED # Log channel ID for logging bot activities

current_custom_status = "under construction" # under construction is the default when it first boots
reaction_cooldowns = defaultdict(float)
active_events = {} # Track events that have a corresponding private chat and event thread 
log = None  # Placeholder for logger




# I log everything in a discord channel instead of a file cuz thats easier
# This function sets up the logging channel... I think... I actually cant read this part 
# All this was written w ChatGPT btw
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
    
    

# Turn unicode names into regular letters, I use fancy fonts a lot hehe
def normalize(text):
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode().lower()



# Takes the text in event message and makes it into a channel name + grabs the date + grabs the event name
def parse_event_info(message_content):
    message_content = normalize(message_content) # take any unicode and make it normal font
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

    # event_date = f"{month} {day}{suffix}"
    channel_date_part = f"{month.lower()}-{day}{suffix}"

    known_events = ["Wii Cook", "Wii Go Out To Eat"]
    line2 = lines[1].strip()
    # Find event name from known_events
    event_name = None
    for base in known_events:
        if re.search(rf'\b{re.escape(base)}\b', line2, re.IGNORECASE):
            event_name = base
            break
    if not event_name:
        if log:
            asyncio.create_task(log.send(f"⚠️ Line2 '{line2}' didn't match any known event names: {known_events}."))
        return None, None, None
    base_event_hyphenated = re.sub(r'\W+', '-', event_name.lower()).strip('-')
    channel_name = f"{base_event_hyphenated}-{channel_date_part}"
    # create datetime object
    try:
        year = datetime.now().year
        try:
            event_date = datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date()
        except ValueError:
            event_date = datetime.strptime(f"{month} {day} {year}", "%b %d %Y").date()
    except ValueError:
        if log:
            asyncio.create_task(log.send(f"⚠️ Failed to convert date: {month} {day}"))
        return None, None


    return event_name, channel_name, event_date










# function to check if Events category is empty, and if it is,
# creates a channel that just says "there are no events at this time"
async def update_no_active_events_voice_channel(guild):
    category = discord.utils.get(guild.categories, id=EVENTS_CATEGORY_ID)
    if not category:
        if log:
            await log.send("⚠️ Events category not found while updating 'no active events' voice channel.")
        return

    # Check if there are any text channels in the category
    text_channels = [ch for ch in category.channels if isinstance(ch, discord.TextChannel)]
    # Find existing "no active events" voice channel if any
    voice_channel_name = "there are no events at this time"
    existing_voice = discord.utils.get(category.voice_channels, name=voice_channel_name)
    if not text_channels:
        # No event text channels exist — create voice channel if it doesn't exist
        if not existing_voice:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False),
                guild.me: discord.PermissionOverwrite(connect=True),
            }
            try:
                await guild.create_voice_channel(
                    voice_channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason="No active event text channels, showing placeholder voice channel."
                )
                if log:
                    await log.send(f"🔈 Created placeholder voice channel '{voice_channel_name}'.")
            except Exception as e:
                if log:
                    await log.send(f"❌ Failed to create placeholder voice channel: {e}")
    else:
        # There are active event text channels — delete the placeholder voice channel if it exists
        if existing_voice:
            try:
                await existing_voice.delete(reason="Active event text channels now present.")
                if log:
                    await log.send(f"🗑 Deleted placeholder voice channel '{voice_channel_name}'.")
            except Exception as e:
                if log:
                    await log.send(f"❌ Failed to delete placeholder voice channel: {e}")











# Startup


@bot.event
async def on_ready():
    await setup_log_channel()
    await log.send(f"Logged in as {bot.user}")
    
    # Set status online default
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.CustomActivity(name=current_custom_status)
    )
    await log.send(f"Status set to **{current_custom_status}**")
    
    # Make sure SERVER_ID is correct
    guild = bot.get_guild(SERVER_ID)
    if not guild:
        await log.send("Guild not found!")
        return
    
    # Make sure Events channel exists
    events_channel = discord.utils.get(guild.text_channels, id=EVENTS_CHANNEL_ID)
    events_category = discord.utils.get(guild.categories, id=EVENTS_CATEGORY_ID)
    if not events_channel or not events_category:
        await log.send("One or more required channels/categories are missing.")
        return
    
    # Rebuild active_events
    global active_events
    active_events.clear()
    private_channels = {channel.name: channel for channel in events_category.text_channels}
    debug_lines = []
    #debug_lines.append(f"Found {len(private_channels)} private channels in Events category:")
    #for name in private_channels.keys():
    #    debug_lines.append(f"  {name}")
    messages = [msg async for msg in events_channel.history(limit=4)]  
    recovered = 0
    skipped_author = 0
    skipped_parse = 0
    skipped_missing_channel = 0
    for msg in messages:
        if msg.author.id != AUTHOR_ID:
            skipped_author += 1
            continue
        try:
            event_name, channel_name, event_date = parse_event_info(msg.content)
        except Exception as e:
            debug_lines.append(f"  Failed to parse event info for message {msg.id}: {e}")
            skipped_parse += 1
            continue
        if not event_name or not channel_name:
            skipped_missing_channel += 1
            continue
        private_channel = private_channels.get(channel_name)
        if not private_channel:
            skipped_missing_channel += 1
            continue
        existing_threads = [t for t in msg.channel.threads if t.name == f"{channel_name}"]
        if existing_threads:
            thread = existing_threads[0]
        else:
            thread = await msg.create_thread(name=f"{channel_name}", auto_archive_duration=10080)
            await thread.send("This is a thread for attendance notices.")
            await thread.edit(locked=True, archived=False)
        active_events[msg.id] = {
            "thread": thread,
            "channel": private_channel,
            "event_date": event_date,
            "reminders_sent": set(),
        }

        recovered += 1
        # Ensure message is cached
        try:
            fetched_msg = await events_channel.fetch_message(msg.id)
            for reaction in fetched_msg.reactions:
                async for user in reaction.users():
                    if user.bot:
                       continue
                    # await log.send(f"[Startup] Detected existing reaction: {reaction.emoji} from {user.display_name} on message {msg.id}")
        except Exception as e:
            await log.send(f"Failed to fetch/cache message {msg.id}: {e}")
        # Ensure reaction is present
        try:
            await msg.add_reaction("👍")
        except discord.errors.Forbidden:
            await log.send("❌ Bot missing permission to add reactions.")
    # Debug summary
    try:
        await log.send("\n".join(debug_lines))
    except Exception as e:
        await log.send(f"Failed to send debug logs: {e}")
    await log.send(
    #    f"✅ Startup Summary\n"
        f"Recovered threads: **{recovered}**\n"
    #    f"- Skipped (author mismatch): **{skipped_author}**\n"
    #    f"- Skipped (parse error): **{skipped_parse}**\n"
    #    f"- Skipped (no channel match): **{skipped_missing_channel}**\n"
    #    f"- Total messages scanned: **{len(messages)}**"
    )

    # Invite tracking
    if guild:
        invites = await guild.invites()
        global invite_uses
        invite_uses = {invite.code: invite.uses for invite in invites}
        
    # start auto message loop
    if not check_event_reminders.is_running():
        check_event_reminders.start()
        
    # check for empty Event category, make channel "there are no events at this time" if applicable
    if guild:
        await update_no_active_events_voice_channel(guild)










# crowd management


# New event message creates corresponding thread and private channel, also saves message id in active_events
@bot.event
async def on_message(message):
    # wait for a message
    await bot.process_commands(message) 
    if message.channel.id != EVENTS_CHANNEL_ID or message.author == bot.user: 
        return 
    # parses event info from message
    event_name, channel_name, event_date = parse_event_info(message.content)
    if not (channel_name and event_date): 
        await log.send(f"❌ Could not parse event from message ID {message.id}")
        return 
    # react w a thumbs up so I know the bot sees the message (also acts as my own count towards attendance)
    await message.add_reaction("\U0001F44D")
    # check for duplicate event
    if message.id in active_events:
        if log:
            await log.send(f"Skipping duplicate event setup for message ID {message.id}")
        return
    # create corresponding thread
    event_thread = await message.create_thread(name=f"{channel_name}", auto_archive_duration=10080)
    await event_thread.send("This is a thread for attendance notices.")
    await event_thread.edit(locked=True, archived=False)
    # make sure Events category exists
    guild = bot.get_guild(SERVER_ID)
    category = discord.utils.get(guild.categories, id=EVENTS_CATEGORY_ID)
    if category is None:
        await log.send(f"⚠️ Events CATEGORY does not exist!!")
    # create corresponding private text channel for event
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False), # members cant see, but bot can
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True),
    }
    private_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
    await update_no_active_events_voice_channel(guild)
    # send initial message in text channel
    if 10 <= event_date.day % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(event_date.day % 10, 'th')
    await private_channel.send(f"This is the chat for those attending {event_name} on {event_date.strftime('%B')} {event_date.day}{suffix}!")
    # put event message in active list with corresponding thread and private channel
    active_events[message.id] = {
        "thread": event_thread,
        "channel": private_channel,
        "event_date": event_date,
        "reminders_sent": set(),
    }
    if log:
        await log.send(f"🆕 Registered new event: msg {message.id} with thread {event_thread.id} and channel {private_channel.id}")



# when user reacts to an event message, adds them to private chat and announces attendance
@bot.event # we use raw instead of regular cuz something about forcefully caching messages ???
async def on_raw_reaction_add(payload):
    # await log.send(f"🔔 RAW ADD triggered by user ID {payload.user_id} on message ID {payload.message_id} in channel ID {payload.channel_id} with emoji {payload.emoji}")
    # ^ log I dont need anymore
    if payload.user_id == bot.user.id:
        await log.send("⛔ Skipped: Reaction from the bot itself.")
        return
    if payload.guild_id != SERVER_ID:
        await log.send(f"⛔ Skipped: Wrong server ID {payload.guild_id}. Expected {SERVER_ID}")
        return
    if payload.channel_id != EVENTS_CHANNEL_ID:
        # await log.send(f"⛔ Skipped: Reaction in channel ID {payload.channel_id}, not EVENTS_CHANNEL_ID.")
        return
    if str(payload.emoji) != "👍":
        await log.send(f"⛔ Skipped: Reaction with emoji {payload.emoji} not 👍")
        return
    try:
        message_id = payload.message_id
        if message_id not in active_events:
            await log.send(f"⚠️ RAW ADD ignored — message ID {message_id} not in active_events.")
            return
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            await log.send("❌ Could not fetch guild object.")
            return
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        if not member:
            await log.send(f"❌ Could not fetch member object for user ID {payload.user_id}")
            return
        display_name = member.nick if member.nick else member.name
        # await log.send(f"👤 Member resolved: {display_name}")
        thread = active_events[message_id]["thread"]
        private_channel = active_events[message_id]["channel"]
        # await log.send(f"📌 Event thread ID: {thread.id}, private channel ID: {private_channel.id}")
        
        # spam cooldowns
        now = time.time()
        last_time = reaction_cooldowns.get(payload.user_id, 0)
        if now - last_time < 20:
            await log.send(f"⏱️ Cooldown active for {display_name} ({int(now - last_time)}s since last)")
            # Remove the reaction
            try:
                channel = bot.get_channel(payload.channel_id)
                if not channel:
                    channel = await bot.fetch_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                await message.remove_reaction(payload.emoji, member)
                await log.send(f"↩️ Removed reaction from {display_name} due to cooldown.")
            except Exception as e:
                await log.send(f"❌ Failed to remove reaction from {display_name}: {e}")
            return
        reaction_cooldowns[payload.user_id] = now


        # Grant access
        await private_channel.set_permissions(member, view_channel=True, send_messages=True)
        await private_channel.send(f"{display_name} is attending this event!")
        await thread.send(f"{display_name} is attending this event!")
        # await log.send(f"✅ Access granted and attendance logged for {display_name}")

    except Exception as e:
        await log.send(f"🔥 ERROR in on_raw_reaction_add: {e}")



# when user UNreacts to an event message, removes them from private chat and announces UNattendance
@bot.event
async def on_raw_reaction_remove(payload):
    # await log.send(f"🔔 RAW REMOVE triggered by user ID {payload.user_id} on message ID {payload.message_id} in channel ID {payload.channel_id} with emoji {payload.emoji}")
    # ^ log I dont need anymore
    if payload.user_id == bot.user.id:
        await log.send("⛔ Skipped: Reaction removal by the bot itself.")
        return
    if payload.guild_id != SERVER_ID:
        await log.send(f"⛔ Skipped: Wrong server ID {payload.guild_id}. Expected {SERVER_ID}")
        return
    if payload.channel_id != EVENTS_CHANNEL_ID:
        # await log.send(f"⛔ Skipped: Reaction removal in channel ID {payload.channel_id}, not EVENTS_CHANNEL_ID.")
        return
    if str(payload.emoji) != "👍":
        await log.send(f"⛔ Skipped: Reaction removal with emoji {payload.emoji} not 👍")
        return
    try:
        message_id = payload.message_id
        if message_id not in active_events:
            await log.send(f"⚠️ RAW REMOVE ignored — message ID {message_id} not in active_events.")
            return
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            await log.send("❌ Could not fetch guild object.")
            return
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        if not member:
            await log.send(f"❌ Could not fetch member object for user ID {payload.user_id}")
            return
        display_name = member.nick if member.nick else member.name
        # await log.send(f"👤 Member resolved: {display_name}")
        thread = active_events[message_id]["thread"]
        private_channel = active_events[message_id]["channel"]
        # await log.send(f"📌 Event thread ID: {thread.id}, private channel ID: {private_channel.id}")

        # Revoke access
        await private_channel.set_permissions(member, overwrite=None)
        await private_channel.send(f"{display_name} is no longer attending this event.")
        await thread.send(f"{display_name} is no longer attending this event.")
        # await log.send(f"✅ Access revoked and cancellation logged for {display_name}")

    except Exception as e:
        await log.send(f"🔥 ERROR in on_raw_reaction_remove: {e}")



# Deleting a private channel renders the event inactive by removing from active_events
@bot.event
async def on_guild_channel_delete(channel):
    if not isinstance(channel, discord.TextChannel):
        return
    if channel.category_id == EVENTS_CATEGORY_ID:
        for message_id, data in list(active_events.items()):
            if data["channel"].id == channel.id:
                thread = data["thread"]
                # Attempt to delete the associated thread
                try:
                    await thread.delete()
                    await log.send(f"🧵 Deleted thread '{thread.name}' because linked channel '{channel.name}' was deleted.")
                except Exception as e:
                    if log:
                        await log.send(f"⚠️ Failed to delete thread for message ID {message_id}: {e}")
                # Remove the event from active_events
                active_events.pop(message_id)
                if log:
                    try:
                        await log.send(f"⚠️ Event channel '{channel.name}' deleted. Also removed thread '{thread.name}' and message ID {message_id} from active_events.")
                    except Exception as e:
                        await log.send(f"Logging failed: {e}")
                guild = channel.guild
                await update_no_active_events_voice_channel(guild)





# automatic messages in chats after events
@tasks.loop(hours=2)
async def check_event_reminders():
    #if log:
    #    await log.send("⏰ check_event_reminders() triggered.")
    now = datetime.now(ZoneInfo("America/New_York"))
    today = now.date()
    for msg_id, data in list(active_events.items()):
        thread = data["thread"]
        channel = data["channel"]
        event_date = data["event_date"]
        days_since = (today - event_date).days
        # Ensure we only run this at/near 12:00pm NY time
        if dt_time(12, 0) <= now.time() < dt_time(14, 0):  # 2-hour window (12–2pm)
            if days_since == 1 and "day1" not in data.get("reminders_sent", set()):
                await channel.send("We extend our heartfelt gratitude to all who have graced this event with their presence! Kindly share your photos with us here in chat :)")
                data.setdefault("reminders_sent", set()).add("day1")
            elif days_since == 2 and "day2" not in data.get("reminders_sent", set()):
                await channel.send("Be sure to share your pictures and save the ones you treasure most — this chat will be closed within the next 24 hours!")
                data.setdefault("reminders_sent", set()).add("day2")
            elif days_since == 3 and "day3" not in data.get("reminders_sent", set()):
                if log:
                    await log.send(f"⚠️ Reminder: The event channel for {event_date} needs to be deleted soon.")
                data.setdefault("reminders_sent", set()).add("day3")











# Bot statuses: !dnd is do not disturb, !on is online, !status rarara sets custom status to rarara


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
        # Keep current presence (dnd/online), only change activity
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

        
        
        
        
        
        
        
        

# Temporary invite code assigns temporary role


TEMP_INVITE_CODE = "NDX4JJhazJ" # Invite code for temporary guests
TEMP_ROLE_ID = 1382502973485355028 # Temporary role given to temporary guests
invite_uses = {} # For tracking temp invites to server


@bot.event
async def on_member_join(member):
    guild = bot.get_guild(SERVER_ID)
    if not guild or member.guild.id != SERVER_ID:
        return
    global invite_uses
    try:
        invites = await guild.invites()
    except discord.Forbidden:
        await log.send("❌ Missing permissions to fetch invites.")
        return
    used_invite = None
    for invite in invites:
        previous_uses = invite_uses.get(invite.code, 0)
        if invite.uses > previous_uses:
            used_invite = invite
            break
    invite_uses = {invite.code: invite.uses for invite in invites}
    if not used_invite:
        await log.send(f"⚠️ Could not determine which invite was used for {member.display_name}")
        return
    if used_invite.code == TEMP_INVITE_CODE:
        role = guild.get_role(TEMP_ROLE_ID)
        if role:
            try:
                await member.add_roles(role, reason=f"Joined via invite {used_invite.code}")
                await log.send(f"✅ Assigned role {role.name} to {member.display_name} who joined using invite {used_invite.code}")
            except discord.Forbidden:
                await log.send(f"❌ Missing permission to assign role {role.name} to {member.display_name}")
        else:
            await log.send(f"❌ Role ID {TEMP_ROLE_ID} not found in guild")
            
            
    # update leaderboard to include name
    await update_leaderboard(bot)

# goes w previous line
@bot.event
async def on_member_remove(member):
    # Remove their points entry if present so they don't appear orphaned on the leaderboard
    points, message_id = load_data()
    uid = str(member.id)
    if uid in points:
        del points[uid]
        save_data(points, message_id)
        if log:
            await log.send(f"➖ Removed points entry for {member.display_name} ({uid}) because they left the server.")
    # Update leaderboard
    await update_leaderboard(bot)












# Points system, leaderboard


LEADERBOARD_CHANNEL_ID = 1386236619488493679
POINTS_FILE = 'points.json'


# Load points AND leaderboard message ID from JSON file
def load_data():
    if os.path.exists(POINTS_FILE):
        try:
            with open(POINTS_FILE, 'r') as f:
                data = json.load(f)
            return data.get('points', {}), data.get('leaderboard_message_id')
        except Exception as e:
            print(f"Error loading points file: {e}")
            return {}, None
    return {}, None


# Save points AND leaderboard message ID to JSON file
def save_data(points, leaderboard_message_id):
    try:
        with open(POINTS_FILE, 'w') as f:
            json.dump({
                'points': points,
                'leaderboard_message_id': leaderboard_message_id
            }, f)
        print(f"Points and leaderboard message ID saved: {points}, {leaderboard_message_id}")
    except Exception as e:
        print(f"Error saving points file: {e}")


# Format the leaderboard message
def format_leaderboard_embed(bot):
    # Collect all non-bot members with zero points default
    all_members = {str(member.id): 0 for member in bot.get_all_members() if not member.bot}
    points, _ = load_data()
    for uid in points:
        all_members[uid] = points[uid]
    sorted_users = sorted(all_members.items(), key=itemgetter(1), reverse=True)
    header = (
        "༺｡ .ᘛ𓆩⁺₊⊰✧⊱₊⁺𓆩 𝑀 𓆪⁺₊⊰✧⊱₊⁺𓆪ᘚ. ｡༻\n"
        "# ✧  𝐿𝑒𝑎𝑑𝑒𝑟𝑏𝑜𝑎𝑟𝑑  ✧\n"
        "༺｡ .ᘛ𓆩⁺₊⊰✧⊱₊⁺𓆩 𝑀 𓆪⁺₊⊰✧⊱₊⁺𓆪ᘚ. ｡༻\n\n"
        "Herein is kept the tally of those most oft in attendance at our assemblies.\n\n"
    )
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    # Move host (author) to the top with a 👑
    author_line = None
    non_author_users = []
    for user_id, score in sorted_users:
        mention = f"<@{user_id}>"
        if user_id == str(AUTHOR_ID):
            author_line = f"👑 {mention} — {score} attendance{'s' if score != 1 else ''}"
        else:
            non_author_users.append((user_id, score))
    if author_line:
        lines.append(f"**{author_line}**")
        lines.append("")  # Add space between host and the rest
    # Apply medals to top 3 of the remaining users
    for i, (user_id, score) in enumerate(non_author_users):
        mention = f"<@{user_id}>"
        medal = medals[i] if i < len(medals) else "‣"
        line = f"{medal} {mention} — {score} attendance{'s' if score != 1 else ''}"
        if i < 3:
            line = f"**{line}**"
        lines.append(line)
    embed = discord.Embed(description=header + "\n".join(lines), color=0xffe63b)
    return embed


# update leaderboard message
async def update_leaderboard(bot):
    points, message_id = load_data()
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel:
        await log.send(f"Leaderboard channel not found: ID {LEADERBOARD_CHANNEL_ID}")
        return
    # If no saved message ID, create leaderboard message and save its ID
    if not message_id:
        await log.send("No leaderboard message ID found, creating new message...")
        try:
            embed = format_leaderboard_embed(bot)
            msg = await channel.send(embed=embed)
            message_id = msg.id
            save_data(points, message_id)
            await log.send(f"Created leaderboard message with ID {message_id}")
        except Exception as e:
            await log.send(f"Failed to create leaderboard message: {e}")
        return
    # Else try to fetch and edit existing leaderboard message
    try:
        msg = await channel.fetch_message(message_id)
    except discord.NotFound:
        await log.send("Leaderboard message not found, will create a new one...")
        try:
            embed = format_leaderboard_embed(bot)
            msg = await channel.send(embed=embed)
            message_id = msg.id
            save_data(points, message_id)
            await log.send(f"Created new leaderboard message with ID {message_id}")
        except Exception as e:
            await log.send(f"Failed to create leaderboard message: {e}")
        return
    except discord.Forbidden:
        await log.send("Missing permission to fetch the leaderboard message.")
        return
    except discord.HTTPException as e:
        await log.send(f"HTTPException fetching leaderboard message: {e}")
        return
    # Edit the existing leaderboard message with updated embed
    try:
        embed = format_leaderboard_embed(bot)
        await msg.edit(embed=embed, content=None)
        await log.send("Leaderboard message edited successfully.")
    except discord.Forbidden:
        await log.send("Missing permission to edit the leaderboard message.")
    except discord.HTTPException as e:
        await log.send(f"Failed to update leaderboard: {e}")



# Find member
def find_member_by_name(guild, name_fragment):
    norm_target = normalize(name_fragment)
    for member in guild.members:
        if member.bot:
            continue
        norm_display = normalize(member.display_name)
        norm_username = normalize(member.name)
        if norm_target in norm_display or norm_target in norm_username:
            return member
    return None



# Points commands: !add name gives name 1 point, !remove name takes away 1 point from name
# ^ this works only in the Logs channel, as doing the same commands in a private event channel will add/remove people to the chat

# Helper: find event (msg_id and data) for the current private channel
def find_event_by_channel(channel):
    for msg_id, data in active_events.items():
        ch = data.get("channel")
        if ch and ch.id == channel.id:
            return msg_id, data
    return None, None

# Reworked !add command (dual-purpose: leaderboard in LOG channel, RSVP in event channel)
@bot.command(name="add")
async def add(ctx, *, name: str):
    # Leaderboard use ONLY in Logs channel
    if ctx.channel.id == LOG_CHANNEL_ID:
        # Existing leaderboard logic (unchanged)
        member = find_member_by_name(ctx.guild, name)
        if not member:
            await ctx.send(f"No matching member found for '{name}'.")
            await log.send(f"No match found for name '{name}'")
            return
        points, message_id = load_data()
        user_id = str(member.id)
        points[user_id] = points.get(user_id, 0) + 1
        save_data(points, message_id)
        await ctx.send(f"Awarded 1 point to {member.display_name}.")
        await update_leaderboard(bot)
        return

    # RSVP use only in event private chats
    event_msg_id, data = find_event_by_channel(ctx.channel)
    if not data:
        await ctx.send("This command only works in event private chats or the Logs channel for leaderboard changes.")
        return

    # Restrict who can force-RSVP (you can remove/adjust this)
    if ctx.author.id != AUTHOR_ID:
        await ctx.send("You don't have permission to force RSVP people.")
        return
    member = find_member_by_name(ctx.guild, name)
    if not member:
        await ctx.send(f"No matching member found for '{name}'.")
        return
    display_name = member.display_name
    try:
        private_channel = data["channel"]
        thread = data["thread"]
        # Grant access (same as raw reaction add logic)
        await private_channel.set_permissions(member, view_channel=True, send_messages=True)
        # Announce in private channel and thread
        await private_channel.send(f"{display_name} is attending this event!")
        await thread.send(f"{display_name} is attending this event!")
        await ctx.send(f"✅ {display_name} has been force-RSVP'd and given access.")
    except Exception as e:
        await ctx.send(f"Failed to RSVP {display_name}: {e}")
        if log:
            await log.send(f"Failed to force-RSVP {display_name} in channel {ctx.channel.id}: {e}")

# Reworked !remove command (dual-purpose: leaderboard in LOG channel, RSVP removal in event channel)
@bot.command(name="remove")
async def remove(ctx, *, name: str):
    # Leaderboard removal ONLY in Logs channel
    if ctx.channel.id == LOG_CHANNEL_ID:
        await log.send(f"Received !remove command from {ctx.author} for name fragment '{name}'.")
        member = find_member_by_name(ctx.guild, name)
        if not member:
            await ctx.send(f"No matching member found for '{name}'.")
            await log.send(f"No match found for name '{name}'")
            return
        points, message_id = load_data()
        user_id = str(member.id)
        if user_id in points and points[user_id] > 0:
            points[user_id] = max(points[user_id] - 1, 0)
            save_data(points, message_id)
            await ctx.send(f"Removed 1 point from {member.display_name}.")
            await update_leaderboard(bot)
        else:
            await log.send(f"No points to remove for user {user_id}.")
            await ctx.send(f"{member.display_name} has no points to remove.")
        return

    # RSVP removal only in event private chats
    event_msg_id, data = find_event_by_channel(ctx.channel)
    if not data:
        await ctx.send("This command only works in event private chats or the Logs channel for leaderboard changes.")
        return
    # Restrict who can force-remove (you can remove/adjust this)
    if ctx.author.id != AUTHOR_ID:
        await ctx.send("You don't have permission to force un-RSVP people.")
        return
    member = find_member_by_name(ctx.guild, name)
    if not member:
        await ctx.send(f"No matching member found for '{name}'.")
        return
    display_name = member.display_name
    try:
        private_channel = data["channel"]
        thread = data["thread"]
        # Revoke access
        await private_channel.set_permissions(member, overwrite=None)
        # Announce in private channel and thread
        await private_channel.send(f"{display_name} is no longer attending this event.")
        await thread.send(f"{display_name} is no longer attending this event.")
        await ctx.send(f"✅ {display_name} has been force-unRSVP'd and access revoked.")
        # Try to remove the user's 👍 reaction from the original announcement message
        try:
            events_channel = bot.get_channel(EVENTS_CHANNEL_ID) or await bot.fetch_channel(EVENTS_CHANNEL_ID)
            if events_channel and event_msg_id:
                orig_msg = await events_channel.fetch_message(int(event_msg_id))
                # Remove the user's 👍 if present
                await orig_msg.remove_reaction("👍", member)
        except Exception as e:
            # Non-fatal — just log
            if log:
                await log.send(f"Failed to remove 👍 from original message {event_msg_id} for {display_name}: {e}")
    except Exception as e:
        await ctx.send(f"Failed to un-RSVP {display_name}: {e}")
        if log:
            await log.send(f"Failed to force-unRSVP {display_name} in channel {ctx.channel.id}: {e}")

