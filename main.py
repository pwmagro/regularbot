#!/usr/bin/python

###############################
# Imports
###############################
import discord 
import traceback
import os
import signal
from RegularBot.config import RegularBotConfig
from RegularBot.client import RegularBotClient
from RegularBot.safe_client import RegularBotSafeClient
from dotenv import load_dotenv
import socket
import time

###############################
# Top level constants
###############################
CRASH_REBOOT_ATTEMPTS = 3
ENV_FILE = ".env"

###############################
# Handle SIGINT
###############################
def interrupt_handler(signum, frame):
    print(f"Got signal {signal.Signals(signum).name}")
    exit(-1)

###############################
# Run
###############################
class RegularBotWrapper:
    def __init__(self):
        # variable that says it's worth trying to reconnect to Discord
        # used by the main retry loop
        # only fatal errors will change this value
        self.willing = True

        # Intents are basically bot features we can disable/enable.
        # Default is fine.
        self.intents = discord.Intents.default()
        self.intents.guild_messages = True
        self.intents.members = True

        # Build the client & grab config
        self.client = RegularBotClient(self.intents)
        self.config = self.client.config

    def load_env(self):
        # Load environment file
        env_path = os.path.abspath(ENV_FILE)
        self.env = load_dotenv(env_path)

    def run(self):
        # Load env
        self.load_env()

        # Get auth key
        key = os.getenv("REGBOT_DISCORD_OAUTH_TOKEN")
        if not key:
            raise ValueError("REGBOT_DISCORD_OAUTH_TOKEN not found in env")
        
        self.client.run(key)    

    def send_crash_notification(self, tb):
        """
        Log in to the bot account with a lightweight client and send a message to bot maintainer(s)
        indicating there was an error.
        Get the maintainers from a list in configs and PM them? Or just ping a role in a private channel?
        """
        print("sending crash notif")

        # Load environment
        self.load_env()

        # Get auth key
        key = os.getenv("REGBOT_DISCORD_OAUTH_TOKEN")
        if not key:
            raise ValueError("REGBOT_DISCORD_OAUTH_TOKEN not found in env")

        temp_client = RegularBotSafeClient(self.intents, self.config, tb)
        temp_client.run(key)

    def get_lock(self):
        # Binding the lock reference to the function itself so it doesn't get
        # garbage collected so long as the wrapper exists
        self._lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

        process_name = self.config['process_name']

        try:
            # The null byte (\0) means the socket is created 
            # in the abstract namespace instead of being created 
            # on the file system itself.
            # Works only in Linux
            self._lock_socket.bind('\0' + process_name)
            return True
        except socket.error:
            print(f"{process_name} already running, exit")
            return False


if __name__ == "__main__":\
    # Create bot
    w = RegularBotWrapper()
    
    # Check if the bot is already running in another process, and if so, exit
    if not w.get_lock():
        print("Already running in another process")
        exit(0)
    
    signal.signal(signal.SIGINT, interrupt_handler)
    
    reboots = 0
    while reboots <= CRASH_REBOOT_ATTEMPTS and w.willing:
        print(f"reboot attempts: {reboots}")
        reboots += 1
        
        try:
            w.run()

        except Exception as e:
            traceback_fmt = traceback.format_exception(e)

            if reboots > CRASH_REBOOT_ATTEMPTS:
                traceback_fmt.append(f"\nFurthermore, the maximum number of reboot attempts ({CRASH_REBOOT_ATTEMPTS}) has been reached, and the bot will not attempt to reboot again")

            w.send_crash_notification(traceback_fmt)
