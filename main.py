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

        # Load the config
        self.config = RegularBotConfig("config/config.json")

        # Intents are basically bot features we can disable/enable.
        # Default is fine.
        intents = discord.Intents.default()
        intents.guild_messages = True
        intents.members = True
        
        self.client = RegularBotClient(intents, self.config)
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

        # Grabbing all intents to minimize risk of failing here.
        # This only runs for a few seconds, so it's fine
        intents = discord.Intents.all()
        config = RegularBotConfig("config/config.json")
        temp_client = RegularBotSafeClient(intents, config, tb)
        temp_client.run(key)


if __name__ == "__main__":
    
    w = RegularBotWrapper()
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
