"""
Config class for RegularBot. Just a dict with some extra methods.
"""

import json

class EmptyConfigException(BaseException):
    pass

class RegularBotConfig:

    def __init__(self, configPath):
        super().__init__()
        self.settings = {}
        self.load_config(configPath)

    def load_config(self, configPath):
        """
        loads and verifies config from a json file and sets this
        object's elements appropriately
        """

        # TODO check if the config.json actually exists, and if not, create a copy from local constants
        #           Then, exit, since fields such as IDs need to be filled out

        with open(configPath, "r") as f:
            config = json.load(f)
        
        if config:
            # TODO verify all expected settings are present before assigning (and nothing extra is there either)
            # TODO validate the settings (check that all IDs are valid, for example)
            if config['debug']['enabled']:
                print("Loaded config:")
                print(config)
            self.settings = dict(config)
        else:
            raise EmptyConfigException("Config is empty!")
        return config
    
    def __getitem__(self, key):
        return self.settings.__getitem__(key)

