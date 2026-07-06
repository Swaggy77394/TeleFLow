import sys
import config
import asyncio
from core.logger import logger
from database.database import init_db
from core.client import client, bot_client
from loader import load_plugins, load_assistant_plugins

async def start_platform():
    logger.info("Starting TeleFlow platform...")
    
    # Initialize Database
    init_db()
    
    # Load Command/Feature Plugins on correct clients
    load_plugins(client, bot_client)
    
    logger.info("Starting Telegram Clients...")
    
    # Start UserBot client asynchronously
    await client.start()
    me = await client.get_me()
    logger.info(f"TeleFlow UserBot is running as {me.first_name} (@{me.username or ''}) [ID: {me.id}]")
    
    # Start Assistant Bot asynchronously if configured
    bot_me = None
    if bot_client:
        logger.info("Starting Assistant Bot...")
        await bot_client.start(bot_token=config.BOT_TOKEN)
        load_assistant_plugins(bot_client)
        bot_me = await bot_client.get_me()
        logger.info(f"Assistant Bot is running as @{bot_me.username} [ID: {bot_me.id}]")
        
    # Send startup notification to owner
    try:
        # Fetch recent dialogs to populate entity cache
        try:
            await client.get_dialogs(limit=40)
        except Exception as cache_err:
            logger.debug(f"Failed to fetch dialogs for cache: {cache_err}")

        notify_id = config.OWNER_ID if config.OWNER_ID else "me"
        bot_info = f"\n🤖 **Assistant Bot:** @{bot_me.username}" if bot_me else ""
        startup_text = (
            "🚀 **TeleFlow successfully started!**\n\n"
            f"👤 **UserBot Account:** {me.first_name} (@{me.username or ''})\n"
            f"🆔 **ID:** `{me.id}`"
            f"{bot_info}"
        )
        
        try:
            await client.send_message(notify_id, startup_text)
            logger.info(f"Startup notification sent to {notify_id}")
        except ValueError as val_err:
            if notify_id != "me":
                logger.warning(f"Could not resolve owner ID {notify_id}, sending to 'me'. Error: {val_err}")
                await client.send_message("me", startup_text)
                logger.info("Startup notification sent to 'me'")
    except Exception as notify_err:
        logger.warning(f"Failed to send startup notification: {notify_err}")
        
    # Keep both running concurrently in the same event loop
    tasks = [client.run_until_disconnected()]
    if bot_client:
        tasks.append(bot_client.run_until_disconnected())
        
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(start_platform())
    except KeyboardInterrupt:
        logger.info("TeleFlow stopped by user.")
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)
        sys.exit(1)
