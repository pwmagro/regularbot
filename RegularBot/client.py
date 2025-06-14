"""
Discord client for RegularBot.
"""

import discord
import asyncio
import sqlite3
from RegularBot.config import RegularBotConfig

#I modified a file lmao -KT
#I modified it even more xddddd

class RegularBotClient(discord.Client):
    def __init__(self, intents: discord.Intents, cfg: RegularBotConfig, **options):
        super().__init__(intents=intents, options=options)
        
        self.config = cfg
        self.sql_lock = asyncio.Lock()

        conn = sqlite3.connect("db/"+self.config['sql_db'])
        cursor = conn.cursor()
        
        # check if the user table exists
        res = cursor.execute("SELECT name FROM sqlite_master WHERE name='users'")
        user_table = res.fetchone()
        if not user_table:
            print("need to create user_table")
            cursor.execute("CREATE TABLE users(guild_id, user_id, message_count, encouraged, congratulated)")

    async def on_ready(self):
        print(f"Logged in as {self.user}")

    async def on_message(self, message: discord.Message):
        print("got message!")

        # Message info
        author = message.author
        channel = message.channel
        guild = message.guild

        # Ignore bots
        if author.bot or author.system:
            return

        # Ignore blacklisted channels
        if channel.id in self.config['regular']['ignore_channels']:
            return

        # Quit early if user already has the role
        if author.get_role(self.config['regular']['role_id']):
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
                    print(f"user found. message_count={message_count}, encouraged={encouraged}, congratulated={congratulated}")

                # If it's greater than the number indicated in config, give the role
                threshold = self.config['regular']['message_threshold']
                if (message_count >= threshold):
                    # only send the message if they haven't gotten it already
                    # if the message was sent before but role assignment failed for some reason,
                    # this stops us from spamming the user while still reattempting role assignment
                    if not congratulated:
                        reply = self.config['regular']['congrats']
                        reply = reply.format(user=author.display_name, message_count=message_count)
                    give_role = True
                # Or, send a message if it's half of the indicated number (and they haven't gotten
                # a halfway message yet.)
                elif (message_count < threshold) and (message_count >= (threshold / 2)) and (not encouraged):
                    reply = self.config['regular']['encouragement']
                    reply = reply.format(user=author.display_name, message_count=message_count)
                    cursor.execute(f"UPDATE users SET encouraged = {True} WHERE user_id={author.id}")
                # Finally, log the rest of the messages, if debug is enabled.
                elif self.config['debug']['enabled'] and (channel.id == self.config['debug']['channel_id']):
                    print(f"Received message from {author.display_name} in guild {guild.id}, channel {channel.id}")
                    print(f"According to the database, in this guild, user {author.id} has sent **{message_count} messages** and **{"HAS" if encouraged else "HAS NOT"}** received their halfway encouragement message")

                # Increment the message count
                cursor.execute(f"UPDATE users SET message_count = {message_count} WHERE user_id={author.id}")
            
            finally:
                # Write out the database
                conn.commit()
                conn.close()
        
        # send a reply, if we have one
        if reply:
            await message.reply(reply)

        # attempt to give the role
        if give_role:
            role_id = self.config['regular']['role_id']
            role_snowflake = guild.get_role(role_id)
            if role_snowflake:
                await author.add_roles(role_snowflake)
            else:
                print(f"Can't find role {role_id}")
                print(f"Available roles: {[r for r in message.guild.roles]}")
