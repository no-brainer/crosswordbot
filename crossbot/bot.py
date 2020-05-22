"""
This module contains various handlers for the bot as well as the initialization function
"""
from enum import IntEnum, auto
import logging
import random

from telegram.ext import Filters, Updater, CommandHandler, ConversationHandler, MessageHandler

from crossbot.crossword import Crossword
import crossbot.settings as settings


logger = logging.getLogger(__name__)


class CrosswordState(IntEnum):
    WAITING_ANSWERS = auto()


def on_error(update, context):
    """
    Logs context errors
    """
    logger.warning("Error %s was caused by update %s", context.error, update)

def on_start(update, context):
    """
    Prints introduction and explains commands
    """
    update.message.reply_text(settings.START_MSG)

def on_new_crossword(update, context):
    update.message.reply_text(settings.LOADING_MSG)
    cw = Crossword(random.randint(1, settings.MAX_CROSSWORD_ID))
    update.message.reply_text(settings.READY_MSG)
    update.message.reply_text(photo=cw.img_link)
    return ConversationHandler.END


def on_ans(update, context):
    pass

def on_timeout(update, context):
    update.message.reply_text(settings.TIMEOUT_MSG)
    return ConversationHandler.END

def on_cancel(update, context):
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
            CrosswordState.WAITING_ANSWERS: [
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
