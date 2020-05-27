"""
This module contains various handlers for the bot as well as the initialization function
"""
from enum import IntEnum, auto
import logging
import random
import sys
import traceback

from telegram import InputMediaPhoto, ParseMode
from telegram.ext import Filters, Updater, CommandHandler, ConversationHandler, MessageHandler
from telegram.utils.helpers import mention_html

from crossbot.crossword import Crossword
import crossbot.settings as settings


logger = logging.getLogger(__name__)


class ConversationState(IntEnum):
    WAITING_ANSWERS = auto()


class StoredValue(IntEnum):
    CROSSWORD_MSG_ID = auto()
    QUESTION_MSG_ID = auto()
    CROSSWORD_STATE = auto()


def on_error(update, context):
    """
    Logs context errors
    """
    if update.effective_message:
        update.effective_message.reply_text(settings.ERROR_USER_MSG)
    trace = "".join(traceback.format_tb(sys.exc_info()[2]))

    payload = ""
    if update.effective_user:
        payload += f" with the user {mention_html(update.effective_user.id, update.effective_user.first_name)}"
    if update.effective_chat:
        payload += f" within the chat <i>{update.effective_chat.title}</i>"
        if update.effective_chat.username:
            payload += f" (@{update.effective_chat.username})"
    if update.poll:
        payload += f" with the poll id {update.poll.id}."
    text = (
        f"Hey.\n The error <code>{context.error}</code> happened{payload}. "
        f"The full traceback:\n\n<code>{trace}</code>"
    )
    for admin_id in settings.ADMINS:
        context.bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)

def on_start(update, _):
    """
    Prints introduction and explains commands
    """
    update.message.reply_html(settings.START_MSG)

def on_new_crossword(update, context):
    """
    Pulls a random crossword and sends it to chat
    """
    chat_id = update.message.chat_id
    context.bot.send_message(chat_id=chat_id, text=settings.LOADING_MSG)
    is_created = False
    while not is_created:
        try:
            cwrd = Crossword(random.randint(1, settings.MAX_CROSSWORD_ID))
        except Exception:
            continue
        is_created = True
    context.chat_data[StoredValue.CROSSWORD_STATE] = cwrd
    context.bot.send_message(chat_id=chat_id, text=settings.READY_MSG)
    question_msg = context.bot.send_message(
        chat_id=chat_id,
        text=settings.QUESTIONS_TEMPLATE_MSG.format(*cwrd.list_unattempted_questions()),
        parse_mode=ParseMode.HTML,
    )
    cwrd_msg = update.message.reply_photo(photo=cwrd.cur_state())
    context.chat_data[StoredValue.CROSSWORD_MSG_ID] = cwrd_msg.message_id
    context.chat_data[StoredValue.QUESTION_MSG_ID] = question_msg.message_id
    return ConversationState.WAITING_ANSWERS

def on_repost(update, context):
    """
    Sends a new message with crossword state
    """
    cwrd_msg = context.bot.send_photo(
        chat_id=update.message.chat_id,
        reply_to_message_id=context.chat_data[StoredValue.QUESTION_MSG_ID],
        photo=context.chat_data[StoredValue.CROSSWORD_STATE].cur_state(),
    )
    context.chat_data[StoredValue.CROSSWORD_MSG_ID] = cwrd_msg.message_id
    return ConversationState.WAITING_ANSWERS

def on_ans(update, context):
    if not context.args or context.args[0][0] not in ["H", "V"]:
        update.message.reply_markdown_v2(settings.INCORRECT_FORMAT_MSG)
        return ConversationState.WAITING_ANSWERS
    args = context.args.copy()
    if len(args) < 2:
        args.append('')
    try:
        context.chat_data[StoredValue.CROSSWORD_STATE].set_answer(*context.args)
    except ValueError as e:
        update.message.reply_text(e.args[0])
    new_im = InputMediaPhoto(media=context.chat_data[StoredValue.CROSSWORD_STATE].cur_state())
    context.bot.edit_message_media(
        chat_id=update.message.chat_id,
        message_id=context.chat_data[StoredValue.CROSSWORD_MSG_ID],
        media=new_im,
    )
    return ConversationState.WAITING_ANSWERS

def on_q(update, context):
    """
    Sends a message with a list of unattempted questions
    """
    cwrd = context.chat_data[StoredValue.CROSSWORD_STATE]
    question_msg = context.bot.send_message(
        chat_id=update.message.chat_id,
        text=settings.QUESTIONS_TEMPLATE_MSG.format(*cwrd.list_unattempted_questions()),
        parse_mode=ParseMode.HTML,
    )
    context.chat_data[StoredValue.QUESTION_MSG_ID] = question_msg.message_id
    return ConversationState.WAITING_ANSWERS

def on_check(update, context):
    cwrd = context.chat_data[StoredValue.CROSSWORD_STATE]
    if not cwrd.is_filled:
        update.message.reply_text(settings.NOT_FILLED_MSG)
        return on_q(update, context)
    if cwrd.is_solved:
        context.bot.send_message(
            chat_id=update.message.chat_id,
            text=settings.COMPLETED_MSG,
        )
        return ConversationHandler.END
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text=settings.NOT_COMPLETED_MSG,
    )
    question_msg = context.bot.send_message(
        chat_id=update.message.chat_id,
        text=settings.QUESTIONS_TEMPLATE_MSG.format(*cwrd.list_unsolved_questions()),
        parse_mode=ParseMode.HTML,
    )
    context.chat_data[StoredValue.QUESTION_MSG_ID] = question_msg.message_id
    return ConversationState.WAITING_ANSWERS

def on_autocomplete(update, context):
    context.chat_data[StoredValue.CROSSWORD_STATE].complete_crossword()
    new_im = InputMediaPhoto(media=context.chat_data[StoredValue.CROSSWORD_STATE].cur_state())
    context.bot.edit_message_media(
        chat_id=update.message.chat_id,
        message_id=context.chat_data[StoredValue.CROSSWORD_MSG_ID],
        media=new_im,
    )
    return ConversationHandler.END

def on_timeout(update, context):
    """
    Warns about timeout, shows correct answers, and exits
    """
    context.chat_data.clear()
    update.message.reply_text(settings.TIMEOUT_MSG)
    return on_autocomplete(update, context)

def on_cancel(update, context):
    """
    Prints cancellation message on command
    """
    context.chat_data.clear()
    update.message.reply_text(settings.CANCEL_MSG)
    return ConversationHandler.END

def prepare_updater():
    """
    Sets up the bot
    """
    updater = Updater(settings.TG_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", on_start))
    dispatcher.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("newcrossword", on_new_crossword),
        ],
        states={
            ConversationState.WAITING_ANSWERS: [
                CommandHandler("ans", on_ans),
                CommandHandler("autocomplete", on_autocomplete),
                CommandHandler("check", on_check),
                CommandHandler("q", on_q),
                CommandHandler("repost", on_repost),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(Filters.all, on_timeout),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", on_cancel)
        ],
        conversation_timeout=settings.CROSSWORD_TIMEOUT,
        per_user=False,
    ))

    dispatcher.add_error_handler(on_error)

    return updater
