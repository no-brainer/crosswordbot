"""
This module contains various constants and environment variables
"""
from os import getenv

from emoji import emojize


# Environment variables
PORT = int(getenv("PORT", "8443"))
HEROKU_APP_NAME = getenv("APP_NAME")
MODE = getenv("MODE", "DEBUG")

TG_TOKEN = getenv("TG_TOKEN")

# Constants
CROSSWORD_TIMEOUT = 25 * 60
MAX_CROSSWORD_ID = 5000

# String literals
START_MSG = emojize(
    u"Привет, фанат кроссвордов\! \U0001F9E0\n\n"
    "Для того, чтобы получить кроссворд, используй команду /newcrossword\. "
    "От кроссворда можно отказаться при помощи /cancel\.\n\n"
    "Если знаешь ответ на вопрос с номером `x` по горизонтали, "
    "то используй команду /ans в формате `/ans Hx ответ`\. "
    "Для ответа на вопрос по вертикали нужно пользоваться форматом `/ans Vx ответ`\n\n"
    "Приятной игры\!"
)
TIMEOUT_MSG = emojize(
    u"Новых ответов не было уже очень давно. \U0001F634\n\n"
    "Я засыпаю, а ответы на этот кроссворд больше не принимаются."
)
CANCEL_MSG = emojize(
    u"Кроссворд забыт \U0001F648"
)
INCORRECT_FORMAT_MSG = (
    u"Неверный формат\.\n\n"
    "Если знаешь ответ на вопрос с номером `x` по горизонтали, "
    "то используй команду /ans в формете `/ans Hx ответ`\. "
    "Для ответа на вопрос по вертикали нужно пользоваться форматом `/ans Vx ответ`"
)
LOADING_MSG = (
    u"Загружаю и обрабатываю кроссворд..."
)
READY_MSG = (
    u"Готово!"
)
QUESTIONS_TEMPLATE_MSG = (
    u"<b>По вертикали:</b>\n"
    "{}\n"
    "<b>По горизонали:</b>\n"
    "{}"
)
ANSWER_TOO_LONG_MSG = (
    u"Ответ слишком длинный. Стоит попробовать что-нибудь другое"
)
ANSWER_TOO_SHORT_MSG = (
    u"Ответ очень короткий. Стоит попробовать что-нибудь другое"
)
