from telethon import events
from telethon.errors import (
    ChatAdminRequiredError, ChatWriteForbiddenError, FloodWaitError,
    UserBannedInChannelError, ChannelPrivateError, UserNotParticipantError
)
from telethon.tl.types import MessageMediaWebPage
from database.database import (
    get_targets_for_source, get_replacements, get_header_footer,
    save_message_map, get_mapped_message,
    is_regex_enabled, get_regex_rules,
    get_media_filters
)
from core.logger import logger
import asyncio
import re

async def copy_message(client, target_id, message, text, reply_to_id=None, entities=None,
                       media_allowed=1, text_allowed=1, reply_markup_override=None):
    """Sends a copy of the message (re-sending media or text) to target_id.
    Preserves formatting_entities (premium emoji, bold, italic, spoiler, etc.)
    when provided and text is unmodified.

    media_allowed: 1 = send the file, 0 = send only text/caption (or skip if text_allowed=0 too)
    text_allowed:  1 = include caption/text, 0 = send media with empty caption
    reply_markup_override: None = keep original, [] = strip all buttons
    """
    # Link previews (MessageMediaWebPage) are not real files — sending them via
    # send_file crashes. Treat these as plain text; Telegram auto-generates the
    # preview from the URL inside the text itself.
    is_real_media = message.media and not isinstance(message.media, MessageMediaWebPage)

    # Determine what to send
    send_media = is_real_media and bool(media_allowed)
    caption    = text if text_allowed else ""
    cap_ents   = entities if text_allowed else None

    # Resolve reply markup
    if reply_markup_override is not None:
        # [] means strip buttons → pass None to Telethon (no markup)
        markup = None
    else:
        markup = message.reply_markup if message.reply_markup else None

    if send_media:
        # Check if this media type supports caption
        supports_cap = True
        if message.sticker or message.poll or message.contact or message.geo or message.venue:
            supports_cap = False

        final_caption  = caption if supports_cap else None
        final_cap_ents = cap_ents if supports_cap else None

        return await client.send_file(
            target_id,
            file=message.media,
            caption=final_caption,
            formatting_entities=final_cap_ents,
            reply_to=reply_to_id,
            buttons=markup
        )
    else:
        # Media is off (or no media) — send text/caption only
        return await client.send_message(
            target_id,
            message=caption,
            formatting_entities=cap_ents,
            reply_to=reply_to_id,
            buttons=markup
        )

def format_inline_buttons(reply_markup):
    """Formats inline keyboard buttons to text markdown links/labels."""
    if not reply_markup:
        return ""
    from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonUrl
    if not isinstance(reply_markup, ReplyInlineMarkup):
        return ""
    
    lines = []
    for row in reply_markup.rows:
        row_str = []
        for button in row.buttons:
            if isinstance(button, KeyboardButtonUrl):
                row_str.append(f"[{button.text}]({button.url})")
            else:
                row_str.append(f"[{button.text}]")
        if row_str:
            lines.append(" | ".join(row_str))
    
    if lines:
        return "\n\n" + "\n".join(lines)
    return ""

def register(client):
    @client.on(events.NewMessage)
    async def forwarder_handler(event):
        # Skip userbot commands (starting with a period or slash)
        if event.text and (event.text.strip().startswith('.') or event.text.strip().startswith('/')):
            return

        chat_id = event.chat_id
        if not chat_id:
            return

        # Query target channels for the current source chat ID
        targets = get_targets_for_source(chat_id)
        if not targets:
            return

        logger.info(f"New message {event.id} in source {chat_id}. Processing for targets: {targets}")

        for target_id in targets:
            try:
                # ─── Resolve Reply Mapping ───────────────────────────────────
                reply_to_msg_id = None
                if event.message.reply_to:
                    source_reply_id = event.message.reply_to.reply_to_msg_id
                    mapped_reply_id = get_mapped_message(chat_id, source_reply_id, target_id)
                    if mapped_reply_id:
                        reply_to_msg_id = mapped_reply_id
                        logger.info(f"Resolved reply mapping: Source Msg {source_reply_id} -> Target Msg {mapped_reply_id}")

                # ─── Resolve Replacements & Header/Footer ───────────────────
                replacements = get_replacements(chat_id, target_id)
                header, footer = get_header_footer(chat_id, target_id)
                regex_active = is_regex_enabled(chat_id) and bool(get_regex_rules(chat_id))
                has_transformations = bool(replacements or header or footer or regex_active)

                # Get text/caption
                original_text = event.message.text or ""
                transformed_text = original_text

                # Apply replacements  [Priority 1 — plain str.replace]
                for find, replace in replacements:
                    transformed_text = transformed_text.replace(find, replace)

                # Apply regex rules  [Priority 2 — only if regex enabled for this source]
                if is_regex_enabled(chat_id):
                    regex_rules = get_regex_rules(chat_id)
                    for rule_name, pattern, replacement in regex_rules:
                        try:
                            transformed_text = re.sub(pattern, replacement, transformed_text)
                        except re.error as rx_err:
                            logger.warning(
                                f"Msg {event.id}: invalid regex pattern '{pattern}' "
                                f"(rule '{rule_name}') — skipping. Error: {rx_err}"
                            )

                # ─── Detect Message Type ─────────────────────────────────────
                msg = event.message
                is_real_media = msg.media and not isinstance(msg.media, MessageMediaWebPage)

                is_gif = False
                if msg.document:
                    from telethon.tl.types import DocumentAttributeAnimated
                    if any(isinstance(x, DocumentAttributeAnimated) for x in msg.document.attributes):
                        is_gif = True

                if msg.sticker:
                    msg_media_type = "sticker"
                elif is_gif:
                    msg_media_type = "gif"
                elif msg.photo:
                    msg_media_type = "photo"
                elif msg.audio:
                    msg_media_type = "audio"
                elif msg.video:
                    msg_media_type = "video"
                elif is_real_media:
                    msg_media_type = "photo"  # fallback for unknown media
                else:
                    msg_media_type = "text"

                has_inline_buttons = bool(msg.reply_markup)

                # ─── Apply Media Filters ──────────────────────────────────────
                filters = get_media_filters(chat_id, target_id)
                media_allowed = filters.get(msg_media_type, 1)
                text_allowed  = filters.get("text", 1)
                btn_allowed   = filters.get("inline_btn", 1)

                if is_real_media:
                    if not media_allowed and not text_allowed:
                        # Both off → skip entirely
                        logger.debug(f"Msg {event.id}: skipped for {target_id} (media+text both OFF)")
                        continue
                else:
                    # Pure text message
                    if not text_allowed:
                        logger.debug(f"Msg {event.id}: skipped for {target_id} (text OFF)")
                        continue

                # Append Inline Buttons as text links if filter is ON
                if has_inline_buttons and btn_allowed:
                    buttons_text = format_inline_buttons(msg.reply_markup)
                    if buttons_text:
                        transformed_text = f"{transformed_text}{buttons_text}"

                # Apply Header & Footer  [Priority 3]
                if header:
                    transformed_text = f"{header}\n\n{transformed_text}"
                if footer:
                    transformed_text = f"{transformed_text}\n\n{footer}"

                # ─── Preserve Premium Formatting Entities ────────────────────
                entities_to_send = None
                if not has_transformations:
                    entities_to_send = event.message.entities
                else:
                    if event.message.entities:
                        logger.debug(
                            f"Msg {event.id}: text transformed, dropping original "
                            f"formatting entities to avoid offset mismatch."
                        )

                # Strip inline buttons if filter is off
                reply_markup_override = None  # None = keep original
                if has_inline_buttons and not btn_allowed:
                    reply_markup_override = []  # empty = strip buttons

                # ─── Always Use Copy Mode (no "Forwarded from" tag) ──────────
                sent_msg = await copy_message(
                    client, target_id, event.message, transformed_text,
                    reply_to_id=reply_to_msg_id, entities=entities_to_send,
                    media_allowed=media_allowed, text_allowed=text_allowed,
                    reply_markup_override=reply_markup_override
                )
                logger.info(f"Copied msg {event.id}: {chat_id} → {target_id} (Copy Mode)")

                # ─── Save Message Mapping for Syncing ────────────────────────
                if sent_msg:
                    save_message_map(chat_id, event.id, target_id, sent_msg.id)
                    logger.debug(f"Saved message mapping: Source {chat_id}:{event.id} -> Target {target_id}:{sent_msg.id}")

            except FloodWaitError as fw:
                logger.warning(f"FloodWait {fw.seconds}s for target {target_id}. Waiting...")
                await asyncio.sleep(fw.seconds + 2)
                # Retry once, still in Copy Mode
                try:
                    sent_msg = await copy_message(
                        client, target_id, event.message, transformed_text,
                        reply_to_id=reply_to_msg_id, entities=entities_to_send,
                        media_allowed=media_allowed, text_allowed=text_allowed,
                        reply_markup_override=reply_markup_override
                    )
                    if sent_msg:
                        save_message_map(chat_id, event.id, target_id, sent_msg.id)
                        logger.info(f"Copied msg {event.id} after FloodWait: {chat_id} → {target_id}")
                except Exception as retry_err:
                    logger.error(f"Retry failed after FloodWait: {retry_err}")

            except ChatWriteForbiddenError:
                logger.error(
                    f"❌ Cannot write to target {target_id}. Reason: Chat write forbidden. "
                    f"The UserBot might be muted/restricted, or the group has slow mode/restricted posting rights."
                )
            except ChatAdminRequiredError:
                logger.error(
                    f"❌ Cannot write to target {target_id}. Reason: Admin permissions required. "
                    f"The UserBot needs administrative privileges to post in this channel/group."
                )
            except UserBannedInChannelError:
                logger.error(
                    f"❌ Cannot write to target {target_id}. Reason: UserBot is banned/restricted in this channel."
                )
            except ChannelPrivateError:
                logger.error(
                    f"❌ Cannot write to target {target_id}. Reason: Target channel is private, or the UserBot has no access."
                )
            except UserNotParticipantError:
                logger.error(
                    f"❌ Cannot write to target {target_id}. Reason: UserBot is not a participant of this group/channel."
                )
            except Exception as e:
                logger.error(
                    f"❌ Failed to process msg {event.id} from {chat_id} to {target_id}. Unexpected error: {e}",
                    exc_info=True
                )

