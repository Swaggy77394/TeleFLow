import sqlite3
import os
from core.logger import logger

DB_PATH = "data/userbot.db"

def init_db():
    """Initializes the database and creates the necessary tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Existing forwards table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS forwards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            UNIQUE(source_id, target_id)
        )
    """)
    
    # Super users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS super_users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    
    # Replacements table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS replacements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER, -- NULL means global replacement for the source chat across all targets
            find_text TEXT NOT NULL,
            replace_text TEXT NOT NULL,
            UNIQUE(source_id, target_id, find_text)
        )
    """)
    
    # Header & Footer table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS header_footer (
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            header TEXT,
            footer TEXT,
            PRIMARY KEY(source_id, target_id)
        )
    """)
    
    # Message mapping table for Edit/Delete/Reply Sync
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message_map (
            source_id INTEGER NOT NULL,
            source_msg_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            target_msg_id INTEGER NOT NULL,
            PRIMARY KEY(source_id, source_msg_id, target_id)
        )
    """)
    
    # Per-source regex ON/OFF toggle
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_settings (
            source_id INTEGER PRIMARY KEY,
            regex_enabled INTEGER DEFAULT 0
        )
    """)

    # Named regex rules per source chat
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regex_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            rule_name TEXT NOT NULL,
            pattern TEXT NOT NULL,
            replacement TEXT NOT NULL,
            created_at INTEGER DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
            UNIQUE(source_id, rule_name)
        )
    """)

    # Per source→target media type filters
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_filters (
            source_id   INTEGER NOT NULL,
            target_id   INTEGER NOT NULL,
            text        INTEGER DEFAULT 1,
            sticker     INTEGER DEFAULT 1,
            photo       INTEGER DEFAULT 1,
            audio       INTEGER DEFAULT 1,
            video       INTEGER DEFAULT 1,
            gif         INTEGER DEFAULT 1,
            inline_btn  INTEGER DEFAULT 1,
            PRIMARY KEY (source_id, target_id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("SQLite Database initialized successfully.")

# ─── FORWARD RULES ────────────────────────────────────────────────────────────

def add_forward_rule(source_id: int, target_id: int):
    """Adds a new forwarding link to the database or activates it."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO forwards (source_id, target_id, is_active) VALUES (?, ?, 1)",
            (source_id, target_id)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding forward rule: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def remove_forward_rule(source_id: int, target_id: int):
    """Removes a forwarding link from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM forwards WHERE source_id = ? AND target_id = ?",
            (source_id, target_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error removing forward rule: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def get_forward_rules():
    """Returns all configured forwarding rules."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT source_id, target_id, is_active FROM forwards")
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error fetching forward rules: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def get_targets_for_source(source_id: int):
    """Returns list of active target chat IDs for a given source chat ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT target_id FROM forwards WHERE source_id = ? AND is_active = 1", (source_id,))
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching targets for source {source_id}: {e}", exc_info=True)
        return []
    finally:
        conn.close()

# ─── SUPER USERS ──────────────────────────────────────────────────────────────

def add_super_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO super_users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding super user: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def remove_super_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM super_users WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error removing super user: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def get_super_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id FROM super_users")
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching super users: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def is_super_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM super_users WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking super user status: {e}", exc_info=True)
        return False
    finally:
        conn.close()

# ─── REPLACEMENTS ─────────────────────────────────────────────────────────────

def add_replacement(source_id: int, target_id: int, find_text: str, replace_text: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO replacements (source_id, target_id, find_text, replace_text) VALUES (?, ?, ?, ?)",
            (source_id, target_id, find_text, replace_text)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding replacement: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def remove_replacement(source_id: int, target_id: int, find_text: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        if target_id is None:
            cursor.execute(
                "DELETE FROM replacements WHERE source_id = ? AND target_id IS NULL AND find_text = ?",
                (source_id, find_text)
            )
        else:
            cursor.execute(
                "DELETE FROM replacements WHERE source_id = ? AND target_id = ? AND find_text = ?",
                (source_id, target_id, find_text)
            )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error removing replacement: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def get_replacements(source_id: int, target_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        if target_id is None:
            cursor.execute(
                "SELECT find_text, replace_text FROM replacements WHERE source_id = ? AND target_id IS NULL",
                (source_id,)
            )
        else:
            cursor.execute(
                "SELECT find_text, replace_text FROM replacements WHERE source_id = ? AND (target_id = ? OR target_id IS NULL)",
                (source_id, target_id)
            )
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error fetching replacements: {e}", exc_info=True)
        return []
    finally:
        conn.close()

# ─── HEADER & FOOTER ──────────────────────────────────────────────────────────

def set_header_footer(source_id: int, target_id: int, header: str, footer: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO header_footer (source_id, target_id, header, footer) VALUES (?, ?, ?, ?)
               ON CONFLICT(source_id, target_id) DO UPDATE SET header=excluded.header, footer=excluded.footer""",
            (source_id, target_id, header, footer)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting header/footer: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def get_header_footer(source_id: int, target_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT header, footer FROM header_footer WHERE source_id = ? AND target_id = ?", (source_id, target_id))
        row = cursor.fetchone()
        if row:
            return row[0], row[1]
        return None, None
    except Exception as e:
        logger.error(f"Error fetching header/footer: {e}", exc_info=True)
        return None, None
    finally:
        conn.close()

# ─── MESSAGE MAPPING ──────────────────────────────────────────────────────────

def save_message_map(source_id: int, source_msg_id: int, target_id: int, target_msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO message_map (source_id, source_msg_id, target_id, target_msg_id) VALUES (?, ?, ?, ?)",
            (source_id, source_msg_id, target_id, target_msg_id)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving message map: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def get_mapped_message(source_id: int, source_msg_id: int, target_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT target_msg_id FROM message_map WHERE source_id = ? AND source_msg_id = ? AND target_id = ?",
            (source_id, source_msg_id, target_id)
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error getting mapped message: {e}", exc_info=True)
        return None
    finally:
        conn.close()

def delete_message_map(source_id: int, source_msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM message_map WHERE source_id = ? AND source_msg_id = ?",
            (source_id, source_msg_id)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error deleting message map: {e}", exc_info=True)
        return False
    finally:
        conn.close()

# ─── REGEX RULES ──────────────────────────────────────────────────────────────

def add_regex_rule(source_id: int, rule_name: str, pattern: str, replacement: str):
    """Adds or updates a named regex rule for a source chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO regex_rules (source_id, rule_name, pattern, replacement)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source_id, rule_name)
               DO UPDATE SET pattern=excluded.pattern, replacement=excluded.replacement""",
            (source_id, rule_name, pattern, replacement)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding regex rule: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def remove_regex_rule(source_id: int, rule_name: str):
    """Deletes a named regex rule for a source chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM regex_rules WHERE source_id = ? AND rule_name = ?",
            (source_id, rule_name)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error removing regex rule: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def get_regex_rules(source_id: int):
    """Returns all regex rules for a source chat, ordered by creation time."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT rule_name, pattern, replacement FROM regex_rules "
            "WHERE source_id = ? ORDER BY created_at ASC, id ASC",
            (source_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error fetching regex rules: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def set_regex_enabled(source_id: int, enabled: bool):
    """Enables or disables regex processing for a source chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO chat_settings (source_id, regex_enabled) VALUES (?, ?)
               ON CONFLICT(source_id) DO UPDATE SET regex_enabled=excluded.regex_enabled""",
            (source_id, 1 if enabled else 0)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting regex_enabled: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def is_regex_enabled(source_id: int) -> bool:
    """Returns True if regex processing is enabled for a source chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT regex_enabled FROM chat_settings WHERE source_id = ?",
            (source_id,)
        )
        row = cursor.fetchone()
        return bool(row and row[0])
    except Exception as e:
        logger.error(f"Error checking regex_enabled: {e}", exc_info=True)
        return False
    finally:
        conn.close()

# ─── MEDIA FILTERS ────────────────────────────────────────────────────────────

MEDIA_FILTER_COLUMNS = ["text", "sticker", "photo", "audio", "video", "gif", "inline_btn"]

def get_media_filters(source_id: int, target_id: int) -> dict:
    """Returns dict of media filter states for a source→target link.
    All types default to 1 (enabled) if no row exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT text, sticker, photo, audio, video, gif, inline_btn "
            "FROM media_filters WHERE source_id = ? AND target_id = ?",
            (source_id, target_id)
        )
        row = cursor.fetchone()
        if row:
            return dict(zip(MEDIA_FILTER_COLUMNS, row))
        # Return all-enabled defaults if no row yet
        return {col: 1 for col in MEDIA_FILTER_COLUMNS}
    except Exception as e:
        logger.error(f"Error fetching media filters: {e}", exc_info=True)
        return {col: 1 for col in MEDIA_FILTER_COLUMNS}
    finally:
        conn.close()


def set_media_filter(source_id: int, target_id: int, media_type: str, enabled: bool) -> bool:
    """Toggles a single media type filter for a source→target link."""
    if media_type not in MEDIA_FILTER_COLUMNS:
        logger.error(f"Invalid media_type for filter: {media_type}")
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Ensure row exists first
        cursor.execute(
            "INSERT OR IGNORE INTO media_filters (source_id, target_id) VALUES (?, ?)",
            (source_id, target_id)
        )
        cursor.execute(
            f"UPDATE media_filters SET {media_type} = ? WHERE source_id = ? AND target_id = ?",
            (1 if enabled else 0, source_id, target_id)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting media filter: {e}", exc_info=True)
        return False
    finally:
        conn.close()


def init_media_filters(source_id: int, target_id: int) -> bool:
    """Creates default (all ON) media filter row for a new forward link.
    Safe to call multiple times — uses INSERT OR IGNORE."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO media_filters (source_id, target_id) VALUES (?, ?)",
            (source_id, target_id)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error initializing media filters: {e}", exc_info=True)
        return False
    finally:
        conn.close()
