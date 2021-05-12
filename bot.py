from pytz import timezone
import requests
import logging

import os
from secret import TOKEN
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
    JobQueue
)
from telegram import ReplyKeyboardMarkup, Update, ReplyKeyboardRemove, Bot
from peewee import SqliteDatabase, Model, DateTimeField, CharField, FixedCharField, IntegerField, BooleanField,IntegrityError,DoesNotExist
from datetime import datetime,date
import threading
import time





LIMIT_EXCEEDED_DELAY_INTERVAL = 60 * 5 
API_DELAY_INTERVAL = 180  


STATE, DISTRICT, PINCODE, DONE, AGE, ALERT = range(6)







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
    telegram_id = CharField(max_length=220, unique=True, index=True)
    chat_id = CharField(max_length=220)
    age_limit = IntegerField(default=18)
    district_id = IntegerField(default=0)
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

    context.bot.send_message(chat_id=update.effective_chat.id, text="Hi, I'll tell you if you have available vaccine slots in your district in the near future, \n you can use /reset to delete your data, to continue,   Select your State")
    
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

    return DISTRICT

def district_choice(update, context):
    text = update.message.text
    print(text)
    today = date.today().strftime("%d/%m/%Y")

    # print("hello from district")

    user : User
    try:
        district_id, _ = text.split(".")

    except ValueError:
        district_id = text[:3]
    print(district_id)
    try:
        user, _ = User.get_or_create(telegram_id=update.effective_user.id, district_id=district_id, defaults={
            'chat_id':update.effective_chat.id
        })
        user.save()
    except IntegrityError:
        user = (User
           .replace(telegram_id=update.effective_user.id, district_id=district_id, 
            chat_id=update.effective_chat.id)
           .execute())

    update.message.reply_text(
        "Select Age group: ",
        reply_markup=ReplyKeyboardMarkup([['18+','45+']],one_time_keyboard=True, resize_keyboard=True)

    )
    # print(get_sessions_today(update.effective_user.id))

    return AGE

def age_choice(update, context):
    text = update.message.text

    # user = User.get(User.telegram_id == update.effective_user.id)
    # print(user.district_id)
    # TODO : Save age to filter sessions later

    print(text)
    today = date.today().strftime("%d-%m-%Y")
    
    update.message.reply_text(
        "Setup daily alert? ",
        reply_markup=ReplyKeyboardMarkup([['Yes','Nevermind']],one_time_keyboard=True, resize_keyboard=True)

    )
    
    
    

    return ALERT 
# print(STATE)

def alert_choice(update, context):
    text = update.message.text
    alert = False
    if text=="Yes":
        alert = True

        update.message.reply_text('Daily Alerts Activated, to change settings press /start again or /reset to reset', reply_markup=ReplyKeyboardRemove())
    else:
        update.message.reply_text('Daily Alerts Deactivated, to change settings press /start again or /reset to reset', reply_markup=ReplyKeyboardRemove())
    
    
    user, _ = User.get_or_create(telegram_id=update.effective_user.id)
    user.alert_enabled=alert
    user.save()
    
    
    
    return ConversationHandler.END

def get_sessions_today(user):
    today = date.today().strftime("%d-%m-%Y")
    # user = User.get(User.telegram_id == telegram_id)
    #print("from get_sessions")
    print("district:")
    print(user.district_id)


    r = requests.get("https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByDistrict?district_id="+str(user.district_id)+"&date="+today, headers=headers)
    if(r.status_code != 200):
        send_as_markdown("API Error, please try after some time.", update)
        return DONE


    centers = r.json()['centers']
    number_of_centers = 0
    for center in centers:
        number_of_centers+=1
    
    if number_of_centers > 0 :
        return True

def check_slots_for_all_users(context):
    bot = context.bot
    print("hello scheduler")
    
    for user in User.select():
        print("user:"+str(user))
        
        if(user.alert_enabled):
            if(get_sessions_today(user)):
                bot.send_message(chat_id=user.chat_id,text="Available sessions found for today")
        time.sleep(5)






def done(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"Thank you !\n\nIf you want to start a new search, Press /start again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END

def reset_function(update, context):
    user_id = update.effective_user.id
    try:
        user = User.get(User.telegram_id == update.effective_user.id)
    except DoesNotExist:
        update.effective_chat.send_message("No data exists to delete.")
        return DONE 
    user.delete_instance()
    update.effective_chat.send_message("Your data has been successfully deleted. Click on /start to restart the bot.")

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
            AGE: [
                MessageHandler(Filters.text,
                age_choice
                )
            ],
            DONE: [
                MessageHandler(
                    Filters.regex('^Done$'),done
                )
            ],
            ALERT: [
                MessageHandler(
                    Filters.text,
                    alert_choice
                )
            ]

        },
        fallbacks=[MessageHandler(Filters.regex('^Start$'), start)],
    
    )
    
    # dispatcher.add_handler(start_handler)

    dispatcher.add_handler(conversation_handler)
    reset_handler = CommandHandler('reset', reset_function)
    dispatcher.add_handler(reset_handler)

    updater.start_polling()
    #check_slots_for_all_users()

    # threading.Thread(target=check_slots_for_all_users).start()

    job_queue = updater.job_queue
    
    # check per hour

    job_queue.run_repeating(check_slots_for_all_users,interval=3600,first=0.0)


    updater.idle()

if __name__ == '__main__':
    main()