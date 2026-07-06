import os
import time
from dotenv import load_dotenv

# Record start time for uptime tracking
START_TIME = time.time()

# Load variables from .env file
load_dotenv()

API_ID = os.getenv("API_ID")
if API_ID:
    try:
        API_ID = int(API_ID)
    except ValueError:
        pass

API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

# OWNER_ID can be integer user ID, or string username, or None
OWNER_ID = os.getenv("OWNER_ID")
if OWNER_ID:
    try:
        OWNER_ID = int(OWNER_ID)
    except ValueError:
        pass

# Bot Token for Assistant
BOT_TOKEN = os.getenv("BOT_TOKEN")
