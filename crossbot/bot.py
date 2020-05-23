"""
This module contains various handlers for the bot as well as the initialization function
"""
from enum import IntEnum, auto
import logging
import random

import telegram
from telegram.ext import Filters, Updater, CommandHandler, ConversationHandler, MessageHandler

from crossbot.crossword import Crossword
import crossbot.settings as settings


logger = logging.getLogger(__name__)


class ConversationState(IntEnum):
    WAITING_ANSWERS = auto()


class StoredValue(IntEnum):
    MESSAGE_ID = auto()
    CROSSWORD_STATE = auto()


def on_error(update, context):
    """
    Logs context errors
    """
    logger.warning("Error %s was caused by update %s", context.error, update)

def on_start(update, context):
    """
    Prints introduction and explains commands
    """
    update.message.reply_markdown_v2(settings.START_MSG)

def on_new_crossword(update, context):
    update.message.reply_text(settings.LOADING_MSG)
    cwrd = Crossword(random.randint(1, settings.MAX_CROSSWORD_ID))
    context.chat_data[StoredValue.CROSSWORD_STATE] = cwrd
    update.message.reply_text(settings.READY_MSG)
    update.message.reply_HTML(
        settings.QUESTIONS_TEMPLATE_MSG.format(*cwrd.list_questions())
    )
    cwrd_msg_id = update.message.reply_photo(photo=cwrd.cur_state()).message_id
    context.chat_data[StoredValue.MESSAGE_ID] = cwrd_msg_id
    return ConversationState.WAITING_ANSWERS

def on_ans(update, context):
    if len(context.args) != 2 or context.args[0][0] not in ["H", "V"]:
        update.message.reply_markdown_v2(settings.INCORRECT_FORMAT_MSG)
        return ConversationState.WAITING_ANSWERS
    try:
        context.chat_data[StoredValue.CROSSWORD_STATE].set_answer(context.args[1])
    except ValueError:
        update.message.reply_text(settings.ANSWER_TOO_LONG_MSG)
    context.bot.edit_message_media(
        chat_id=update.message.chat_id,
        message_id=context.chat_data[StoredValue.MESSAGE_ID],
        photo=context.chat_data[StoredValue.CROSSWORD_STATE].cur_state(),
    )
    return ConversationState.WAITING_ANSWERS

def on_timeout(update, context):
    context.chat_data.clear()
    update.message.reply_text(settings.TIMEOUT_MSG)
    return ConversationHandler.END

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
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", on_start))
    dp.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler('newcrossword', on_new_crossword),
        ],
        states={
            ConversationState.WAITING_ANSWERS: [
                CommandHandler('ans', on_ans)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(Filters.all, on_timeout),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', on_cancel)
        ],
        conversation_timeout=settings.CROSSWORD_TIMEOUT,
    ))

    dp.add_error_handler(on_error)

    return updater
