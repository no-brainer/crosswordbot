"""
This module is an entry point
"""
import logging

from crossbot.bot import prepare_updater
from crossbot.settings import HEROKU_APP_NAME, MODE, PORT, TG_TOKEN


logging.basicConfig(
    level=(logging.DEBUG if MODE == 'DEBUG' else logging.INFO),
    format="[%(asctime)s] p%(process)s {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    updater = prepare_updater()
    logging.info("Launching")
    updater.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TG_TOKEN,
    )
    updater.bot.set_webhook(f"https://{HEROKU_APP_NAME}.herokuapp.com/{TG_TOKEN}")
    updater.idle()


if __name__ == "__main__":
    main()
