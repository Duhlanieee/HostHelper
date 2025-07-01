<img src=images/Profile.jpg alt=Discord Server Screenshot width=200 align=right>

# HostHelper
[Here's the code :D](HostHelper.py)

---
As a frequent host in largescale events, this bot serves as my assistant! I have a server in which I organize events that take place at my house, and this bot helps me with crowd management and automated preparation.

---
## "𝑇ℎ𝑒 𝑀𝑖𝑐𝑘𝑙𝑒𝑦 𝐸𝑠𝑡𝑎𝑡𝑒" Discord Server

<img src=images/MobileMembers.png alt=Discord Server Screenshot width=280 align=right>
<img src=images/MobileMain.png alt=Discord Server Screenshot width=280 align=right>
Wrapped in antique elegance and aristocratic aesthetics, "𝑇ℎ𝑒 𝑀𝑖𝑐𝑘𝑙𝑒𝑦 𝐸𝑠𝑡𝑎𝑡𝑒" is a server built to support the community that surrounds me and my house. I've designed and executed this server all on my own, with the help of Sapphire and ChatGPT. Given that this server was meant to be a means of effective planning and communication, I optimized it for mobile use, though it still stands as a capable desktop server despite the emojis rendering a bit different. 

---
The bot's presence in the server acts as a personification of my house. Online means the house is open to visitors, while do not disturb means the house is closed. Fun fact, the pfp is a picture of my dishware! :D

---

<img src=images/Leaderboard.png alt=Discord Server Screenshot width=1050>

---
# So... what does it do?
So glad you asked. I plan on putting some gifs here to explain better but for now have a wall of text.
## Frontend
- Crowd Management:
  
  - When a new event is announced in the "Events" channel, it creates a private text chat dedicated to that event. It also makes a thread where it annouces when someone RSVPs (or denounces their RSVP).![Event](https://github.com/user-attachments/assets/c736c570-7df9-4dde-ab63-8c1b466097dc)
  - Those who RSVP by reacting with 👍 will get access to the private chat, and reaction removals will remove them from the chat.![React](https://github.com/user-attachments/assets/8f131b52-dae1-4145-8e35-c8a099be6f2d)
  - Manages a quiet voice channel called “there are no events at this time,” which appears whenever there are no active events.![Delete](https://github.com/user-attachments/assets/b9ce38ca-1800-454e-9cde-5ac2d4f3d97f)
  - Sends reminders in the private chat asking people to share photos after the event, and warning them when the chat is about to close.

- Manor Disposition:

  - As stated earlier, the status of the bot is a reflection of the status of my house.
  - Online means the house is open to visitors, while do not disturb means it's closed. I alter the state with commands !on and !dnd
  - The custom status can further explain if needed. I alter it with the command !status blah blah blah
  - This function is intended for those who like to show up at my door on a whim, to which they can consult the status before calling me.

- Temporary Roles:

  - Third-party guests who only plan to be at a certain event are invited to the server with a specific code, to which they are automatically given a corresponding role. This role implies that they will only be in the server for the duration of the event. I then kick them afterwards lmao

- Attendance Leaderboard:

  - Self explanatory.
  - !add name and !remove name to add or remove a point.
  - Points are tracked in a JSON file.
 
## Backend
- Pycord:
 
  - discord.py is the default python for writing discord bots, but was archived in 2021 and is no longer maintained. Pycord is a volunteer-made fork of discord.py, but is actively maintained with the most up-to-date features. I realized I had to switch to Pycord when I tried making custom statuses for the bot, which Pycord supports but discord.py does not.
  
- Recovery:

   - This seems simple but took me FOREVER. Discord doesn't allow bots to see messages sent before the bot boots up, so when a power surge happens, my bot can no longer see the messages in the events chat. The on_ready function (runs after a restart) includes code to rebuild its knowledge and in effect forcefully "re-cache" the old event messages so that reactions will still be identified after a restart.
 
- Spam Prevention:

  - Very quickly did my friends realize they could spam the "name is attending" message in the private chat. There's now a cooldown on how often a user can add a reaction lmao
 
- active_events List:

  - After encountering the power surge problem and attempting a recovery method, I realized I had to redo the code so it relies on a list. This list contains each event message id, along with its corresponding thread and private chat. Events in this list are considered active, because I have yet to delete the private chat. Deleting a private chat removes the event from the list. Any reaction on an active event message will trigger crowd management functionalities. This reduces the load on recovery, as it doesn't have to cache every single message posted in Events, and instead, it only reads the most recent 4 and checks to see if its active (has a private chat).
