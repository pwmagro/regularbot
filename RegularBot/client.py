"""
Discord client for RegularBot.
"""

import os
import discord
from discord.ext import tasks
from discord import app_commands
import asyncio
import sqlite3
from random import choice
from RegularBot.config import RegularBotConfig
import traceback

class RegularBotException(Exception):
    """
    Exception class which sends emergency message to maintainers upon creation
    """

    def __init__(self, bot, msg):
        super().__init__(msg)
        print("RegularBotException raised")
        loop = asyncio.get_running_loop()
        loop.create_task(bot.send_exception_msg(self))

class RegularBotClient(discord.Client):
    command_tree: app_commands.CommandTree

    def __init__(self, intents: discord.Intents, **options):
        super().__init__(intents=intents, options=options)
        
        self.refresh_config()
        self.sql_lock = asyncio.Lock()

        if not os.path.isdir("db"):
            os.mkdir("db")

        db_name = "db/"+self.config['sql_db']
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        
        # check if the user table exists
        res = cursor.execute("SELECT name FROM sqlite_master WHERE name='users'")
        user_table = res.fetchone()
        if not user_table:
            print("need to create user_table")
            cursor.execute("CREATE TABLE users(guild_id, user_id, message_count, encouraged, congratulated)")
        
        self.command_tree = app_commands.CommandTree(self)
        self.register_commands()

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        await self.command_tree.sync()
        self.regularbot_change_presence.start()

    async def on_message(self, message: discord.Message):
        # Message info
        author = message.author
        channel = message.channel

        if type(channel) == discord.DMChannel:
            return

        guild = message.guild
        guild_key = str(guild.id)
        
        # Check if the guild config is present
        # TODO make it actually create a default config
        if not (guild_config := self.config['guilds'].get(guild_key)):
            raise RegularBotException(self, f"Guild {guild.id} not present in config file!")

        # Ignore bots
        if author.bot or author.system:
            return

        # Ignore blacklisted channels
        if channel.id in guild_config['regular']['ignore_channels']:
            return

        # Quit early if user already has the role
        if author.get_role(guild_config['regular']['role_id']):
            return
        
        # Need these variables outside of the `async with` scope
        reply = ""
        give_role = False
        message_count = 0
        encouraged = False
        congratulated = False

        # It's very possible for people to send messages faster than the bot
        # can handle them, so we need to ensure database read/write is atomic
        async with self.sql_lock:
            try:
                # load up the database
                conn = sqlite3.connect("db/"+self.config['sql_db'])
                cursor = conn.cursor()

                # Get user's message count, creating a new row in the table if necessary.
                res = cursor.execute(f"SELECT message_count, encouraged, congratulated FROM users WHERE user_id={author.id} AND guild_id={guild.id}")
                db_user = res.fetchone()
                if not db_user:
                    print("user not found, insert into table")
                    cursor.execute(f"INSERT INTO users VALUES ({guild.id}, {author.id}, {0}, {False}, {False})")
                    message_count = 1
                    encouraged = False
                    congratulated = False
                else:
                    message_count = db_user[0] + 1
                    encouraged = db_user[1]
                    congratulated = db_user[2]

                # If it's greater than the number indicated in config, give the role
                threshold = guild_config['regular']['message_threshold']
                if (message_count >= threshold):
                    # only send the message if they haven't gotten it already
                    # if the message was sent before but role assignment failed for some reason,
                    # this stops us from spamming the user while still reattempting role assignment
                    if not congratulated:
                        reply = guild_config['regular']['congrats']
                        reply = reply.format(user=author.display_name, message_count=message_count)
                        cursor.execute(f"UPDATE users SET congratulated = {True} WHERE user_id={author.id} AND guild_id={guild.id}")
                    give_role = True
                # Or, send a message if it's half of the indicated number (and they haven't gotten
                # a halfway message yet.)
                elif (message_count < threshold) and (message_count >= (threshold / 2)) and (not encouraged):
                    reply = guild_config['regular']['encouragement']
                    reply = reply.format(user=author.display_name, message_count=message_count)
                    cursor.execute(f"UPDATE users SET encouraged = {True} WHERE user_id={author.id} AND guild_id={guild.id}")
                # Finally, log the rest of the messages, if debug is enabled.
                elif self.config['debug']['enabled'] and (channel.id == self.config['debug']['channel_id']):
                    print(f"Received message from {author.display_name} in guild {guild.id}, channel {channel.id}")
                    print(f"According to the database, in this guild, user {author.id} has sent **{message_count} messages** and **{"HAS" if encouraged else "HAS NOT"}** received their halfway encouragement message")

                # Increment the message count
                cursor.execute(f"UPDATE users SET message_count = {message_count} WHERE user_id={author.id} AND guild_id={guild.id}")
            
            finally:
                # Write out the database
                conn.commit()
                conn.close()
        
        # send a reply, if we have one
        if reply:
            await message.reply(reply)

        # attempt to give the role
        if give_role:
            role_id = guild_config['regular']['role_id']
            role_snowflake = guild.get_role(role_id)
            if role_snowflake:
                await author.add_roles(role_snowflake)
            else:
                raise RegularBotException(self, f"Can't find role {role_id}.\nAvailable roles: {[r for r in message.guild.roles]}")

    @tasks.loop(hours=1)
    async def regularbot_change_presence(self):
        presences = self.config['presences']

        (activity_text, activity_type_str) = choice([(k,v) for k,v in presences.items()])

        print(f"changing presence to {activity_type_str}: \"{activity_text}\"")

        if activity_type_str == "playing":
            activity_type = discord.ActivityType.playing
        elif activity_type_str == "streaming":
            activity_type = discord.ActivityType.streaming
        elif activity_type_str == "listening":
            activity_type = discord.ActivityType.listening
        elif activity_type_str == "watching":
            activity_type = discord.ActivityType.watching
        else:
            raise RegularBotException(self, f"unknown activity type {activity_type_str}")
            return

        activity = discord.Activity(name=activity_text, type=activity_type)

        await self.change_presence(status=discord.Status.online, activity=activity)

    def refresh_config(self):
        self.config = RegularBotConfig('config/config.json')

    async def send_exception_msg(self, exc):
        traceback_fmt = traceback.format_exception(exc)
        message_text = f"The bot encountered a fatal error with the following details: \n ```{'\n'.join(traceback_fmt)}```"
        for id, info in self.config['maintainers'].items():

            if not info['notify_on_exception']:
                continue
            
            user_id = int(id)
            user = self.get_user(user_id)
            
            if not user.dm_channel:
                print("creating dm...")
                await user.create_dm()
            
            if user.dm_channel:
                await user.dm_channel.send(message_text)

    def register_commands(self):

        @self.command_tree.command(name="rbconfig", description="ONLY bot maintainers (not server admins) can execute this command_2")
        @app_commands.guilds(discord.Object(self.config['debug']['guild_id']))
        async def command_config(ctx):

            maintainers = [int(id) for id in self.config['maintainers']]
            if ctx.user.id not in maintainers:
                await ctx.response.send_message("This is an internal command, and can only be used by bot maintainers. It is not meant to be used by server admins.")

            # Quick'n dirty way for global bot maintainers (and *only* them) to refresh the config
            print("refreshing config...")
            self.refresh_config()
            await ctx.response.send_message("Refreshed config!")
            return

        @self.command_tree.command(name="rbhowfar", description="Check how far you are from reaching Regular status")
        async def command_howfar(ctx):
            user = ctx.user
            guild = ctx.guild
            
            guild_key = str(guild.id)
            
            # Check if the guild config is present
            # TODO make it actually create a default config
            if not (guild_config := self.config['guilds'].get(guild_key)):
                raise RegularBotException(self, f"Guild {guild.id} not present in config file!")

            if user.bot or user.system:
                return
            
            if user.get_role(guild_config['regular']['role_id']):
                await ctx.response.send_message(f"{user.display_name}, you're already a Regular here!")
                return

            async with self.sql_lock:
                try:
                    # load up the database
                    conn = sqlite3.connect("db/"+self.config['sql_db'])
                    cursor = conn.cursor()

                    # Get user's message count, creating a new row in the table if necessary.
                    res = cursor.execute(f"SELECT message_count FROM users WHERE user_id={user.id} AND guild_id={guild.id}")
                    message_count = res.fetchone()[0]
                finally:
                    cursor.close()
            
            if not message_count:
                await ctx.response.send_message(f"{user.display_name}, I've never seen you send a message here!")
                return
            else:
                threshold = guild_config['regular']['message_threshold']

                # handle the case where the user has sent more messages than required, but they don't have the role. This might happen if the role assignment failed.
                if message_count >= threshold:
                    await ctx.response.send_message(f"{user.display_name}, you've already hit the message count needed to be a Regular, but you don't have the role yet. Something might have gone wrong when I tried to give you the role, but don't worry - I'll try again next time you send a message!")
                    return

                await ctx.response.send_message(f"{user.display_name}, you've sent {message_count} messages since I joined the server. That means you've got {threshold - message_count} messages to go. Keep it up!")
                return

        # TODO
        # add a command to edit config
