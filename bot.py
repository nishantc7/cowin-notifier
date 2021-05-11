import requests
import logging

import os
from secret import TOKEN
from telegram.ext import CommandHandler
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)
from telegram import ReplyKeyboardMarkup, Update, ReplyKeyboardRemove
from peewee import SqliteDatabase, Model, DateTimeField, CharField, FixedCharField, IntegerField, BooleanField
from datetime import datetime


STATE, DISTRICT, PINCODE, DONE = range(4)





#print(TOKEN)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


#Using Recommended settings

db = SqliteDatabase('my_app.db', pragmas={
    'journal_mode': 'wal',
    'cache_size': -1 * 64000,  # 64MB
    'ignore_check_constraints': 0,
    'synchronous': 0})


# creating a user model to store data

class User(Model):
    created_on = DateTimeField(default=datetime.now)
    last_alert_sent_at: datetime = DateTimeField(default=datetime.now)
    total_alerts_sent = IntegerField(default=0)
    telegram_id = CharField(max_length=220, unique=True)
    chat_id = CharField(max_length=220)
    age_limit = IntegerField(default=18)
    district_id = IntegerField(default=0)
    state_id = IntegerField(default=0)
    alert_enabled = BooleanField(default=False, index=True)

    class Meta:
        database = db




#using the cowin api



headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}



def create_markup(choice, data) -> list:
    markup = []
    markup_str = ""
    i = 0
    t = []
    for a in data[choice+"s"]:
        markup_str = str(a[choice+'_id'])+". "+a[choice+'_name']
        t.append(markup_str)
        if (i%2) or i == len(data[choice+"s"])-1:
            markup.append(t.copy())
            t.clear()
        i = i+1
    return markup

def start(update, context):

    context.bot.send_message(chat_id=update.effective_chat.id, text="Hi, I'll tell you if you have available vaccine slots in your district in the near future, Select your state to get started")
    
    r = requests.get("https://cdn-api.co-vin.in/api/v2/admin/location/states", headers=headers)
    if(r.status_code != 200):
        send_as_markdown("API Error", update)
        return STATE
    
    states_data = r.json()
    state_markup = create_markup('state', states_data)

    update.message.reply_text(
        "Select state:",
        reply_markup=ReplyKeyboardMarkup(state_markup, one_time_keyboard=True, resize_keyboard=True),
    )

    return STATE


def state_choice(update, context):
    text = update.message.text
    state_id, state_name = text.split(".")

    r = requests.get("https://cdn-api.co-vin.in/api/v2/admin/location/districts/"+state_id, headers=headers)
    if(r.status_code != 200):
        send_as_markdown("API Error", update)
        return DISTRICT
    
    district_data = r.json()
    district_markup = create_markup('district', district_data)
    update.message.reply_text(
        "Select District:",
        reply_markup=ReplyKeyboardMarkup(district_markup, one_time_keyboard=True, resize_keyboard=True)

    )

    user : User
    user, _ = User.get_or_create(telegram_id=update.effective_user.id, state_id=state_id, defaults={
        'chat_id':update.effective_chat.id
    })
    user.save()
    print(update.effective_user.id)
    print(user)
    for user in User.select():
        print(user.state_id)

    return DISTRICT

def district_choice(update, context):
    text = update.message.text
    print(text)
    print("hello from district")
    return DISTRICT
   
# print(STATE)


def main() -> None:
    
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher


    db.connect()
    db.create_tables([User, ])


    conversation_handler = ConversationHandler(
        entry_points = [CommandHandler('start', start)],
        states = {
            STATE: [
                MessageHandler(
                    Filters.text,
                    state_choice
                )
            ],
            DISTRICT: [
                MessageHandler(Filters.text,
                    district_choice
                )

            ],
        },
        fallbacks=[MessageHandler(Filters.regex('^Start$'), start)],
    
    )
    
    # dispatcher.add_handler(start_handler)

    dispatcher.add_handler(conversation_handler)
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()