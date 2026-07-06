import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
import config
from core.logger import logger

# Validate API configuration
if not config.API_ID or not config.API_HASH:
    logger.critical("API_ID and API_HASH must be configured in .env file!")
    sys.exit(1)

# Initialize TelegramClient
if config.SESSION_STRING:
    logger.info("Initializing TelegramClient with StringSession...")
    client = TelegramClient(
        StringSession(config.SESSION_STRING),
        config.API_ID,
        config.API_HASH
    )
else:
    logger.info("Initializing TelegramClient with file-based session (data/teleflow)...")
    # Creates/uses data/teleflow.session file
    client = TelegramClient(
        "data/teleflow",
        config.API_ID,
        config.API_HASH
    )

# Initialize bot client if BOT_TOKEN is present
bot_client = None
if config.BOT_TOKEN:
    logger.info("Initializing Assistant Bot client...")
    bot_client = TelegramClient(
        "data/assistant_bot",
        config.API_ID,
        config.API_HASH
    )
