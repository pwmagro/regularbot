import discord
from RegularBot.config import RegularBotConfig

class RegularBotSafeClient(discord.Client):
    '''
    Mega lightweight client which just sends DMs to the users specified
    in config, letting them know that there was a fatal error in the main
    client.
    '''
    def __init__(self, intents: discord.Intents, cfg: RegularBotConfig, traceback: list[str], **options):
        super().__init__(intents=intents, options=options)
        self.config = cfg
        self.tb = traceback
        print("safe client created")

    async def on_ready(self):
        try:
            print('Logged in as {0}'.format(self.user))

            message_text = f"The bot encountered a fatal error with the following details: \n ```{'\n'.join(self.tb)}```"
            for user_info in self.config['maintainers']:

                if not user_info['notify_on_exception']:
                    continue
                
                user_id = int(user_info["id"])
                print(user_id)
                user = self.get_user(user_id)
                
                if not user.dm_channel:
                    print("creating dm...")
                    await user.create_dm()
                
                if user.dm_channel:
                    await user.dm_channel.send(message_text)
            
        finally:
            await self.close()
