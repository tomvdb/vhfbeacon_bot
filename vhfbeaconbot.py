import logging
from telegram.ext import Updater, CommandHandler, CallbackContext,  CallbackQueryHandler, InlineQueryHandler, ConversationHandler, PicklePersistence, Filters, MessageHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatAction, InlineQueryResultArticle, ParseMode, InputTextMessageContent, ParseMode, Bot
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove)
import os
import time
from functools import wraps
from uuid import uuid4
from telegram.utils.helpers import escape_markdown
from datetime import date
import datetime
from io import BytesIO
import calendar
import sys

# credentials/info - 
# add a telegram token for the bot
TELEGRAMTOKEN = 'insert token here'
# update telegram report group chat id
TELEGRAMREPORTGROUP = -123

BEACONS = [ ['Beacon 1', 'Beacon 2', 'Beacon 3', 'Beacon 4']] 

CALLSIGN, LOCATION, CONFIRM, REPORT, BEACON, RST, CONFIRMREPORT = range(7)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

upper = 'ABCDEFGHIJKLMNOPQRSTUVWX'
lower = 'abcdefghijklmnopqrstuvwx'

def to_grid(dec_lat, dec_lon):
    if not (-180<=dec_lon<180):
        sys.stderr.write('longitude must be -180<=lon<180, given %f\n'%dec_lon)
        sys.exit(32)
    if not (-90<=dec_lat<90):
        sys.stderr.write('latitude must be -90<=lat<90, given %f\n'%dec_lat)
        sys.exit(33) # can't handle north pole, sorry, [A-R]

    adj_lat = dec_lat + 90.0
    adj_lon = dec_lon + 180.0

    grid_lat_sq = upper[int(adj_lat/10)];
    grid_lon_sq = upper[int(adj_lon/20)];

    grid_lat_field = str(int(adj_lat%10))
    grid_lon_field = str(int((adj_lon/2)%10))

    adj_lat_remainder = (adj_lat - int(adj_lat)) * 60
    adj_lon_remainder = ((adj_lon) - int(adj_lon/2)*2) * 60

    grid_lat_subsq = lower[int(adj_lat_remainder/2.5)]
    grid_lon_subsq = lower[int(adj_lon_remainder/5)]

    return grid_lon_sq + grid_lat_sq + grid_lon_field + grid_lat_field + grid_lon_subsq + grid_lat_subsq

def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def send_typing_action(func):
    """Sends typing action while processing func command."""

    @wraps(func)
    def command_func(update, context, *args, **kwargs):
        context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)
        return func(update, context,  *args, **kwargs)

    return command_func    

# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.
@send_typing_action
def start(update, context):
    user_id = update.message.chat_id
    print('Group status: ' + context.bot.get_chat_member(TELEGRAMREPORTGROUP, user_id).status )

    if context.user_data:
        callsign = context.user_data['callsign']
        #lat = context.user_data['lat']
        #lon = context.user_data['lon']
        update.message.reply_text('Welcome ' + callsign + ", you can report a beacon by sending the /report command")
        return REPORT
    else:
        update.message.reply_text('hello, please send me your callsign')
        print(update.message.chat_id)
        return CALLSIGN

@send_typing_action
def test(update, context):
        update.message.reply_text('hello')
        print(update)

def cancel(update, context):
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text('Bye! Please send /reset to restart setup or /start to go into report mode')

    return ConversationHandler.END        

def reset(update, context):
    context.user_data.clear()    
    return start(update,context)        

def callsign(update, context):
    user = update.message.from_user
    callsign = update.message.text
    context.user_data['callsign'] = callsign.upper()
    logger.info("Callsign of %s: %s", user.first_name, update.message.text)
    update.message.reply_text('Hi ' + callsign + ', Now please send me a location pin of your QTH (Used to calculate Grid Locator)')
    return LOCATION    

def start_beacon_report(update, context):
    reply_keyboard = BEACONS
    user = update.message.from_user
    update.message.reply_text('Which beacon did you hear?', reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))    

    return BEACON

def report_beacon(update,context):
    context.user_data['beacon'] = update.message.text
    
    #todo validate beacon name

    update.message.reply_text('Please provide a RST code (3 digits) for your beacon report')    
    return RST

def report_rst(update,context):
    valrst = update.message.text
    valid = True

    # check len
    if len(valrst) != 3:
        valid = False

    # check all numbers
    try:
        a = int(valrst)

        # check first number can't be higher than 5
        t = int(valrst[0])
        if t > 5 or t < 1:
            valid = False
        t = int(valrst[1])
        if t < 1:
            valid = False
        t = int(valrst[2])
        if  t < 1:
            valid = False
    except:
        valid = False

    if valid == False:
        update.message.reply_text('Your RST number does not seem to valid, please only supply a 3 digit value eg. 599' )
        return RST

    context.user_data['rst'] = valrst

    reply_keyboard = [['Yes', 'No']]
    update.message.reply_text('Your Beacon Report for ' + context.user_data['beacon'] + ' is ' + context.user_data['rst'] + ' , please confirm with either Yes or No', reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))

    return CONFIRMREPORT

def confirm_report(update,context):
    result = update.message.text
    if result == 'Yes':
        context.bot.send_message(chat_id=TELEGRAMREPORTGROUP, text=context.user_data['callsign'] + ' heard ' + context.user_data['beacon'] + ' ' + ' at ' + context.user_data['gridlocator'] + ', RST: ' + str(context.user_data['rst']))
        update.message.reply_text('Thanks for confirming, you may now report more beacons using the /report command', reply_markup=ReplyKeyboardRemove())
        return REPORT
    
    update.message.reply_text('Your report has been cancelled, you may now report more beacons using the /report command', reply_markup=ReplyKeyboardRemove())
    return REPORT
    

def report(update, context):
    user = update.message.from_user
    logger.info("Report Data %s: %s", user.first_name, update.message.text)
    update.message.reply_text('You are all setup to report beacons, please use the /report command to report a beacon')    

    return REPORT    

def location(update, context):
    reply_keyboard = [['Yes', 'No']]
    user = update.message.from_user
    user_location = update.message.location
    logger.info("Location of %s: %f / %f", user.first_name, user_location.latitude,
                user_location.longitude)

    #context.user_data['lat'] = user_location.latitude
    #context.user_data['lon'] = user_location.longitude

    context.user_data['gridlocator'] = to_grid(user_location.latitude, user_location.longitude)
    update.message.reply_text('Your info is : \nCallsign : ' + context.user_data['callsign'] + '\nGrid Locator:' + str(context.user_data['gridlocator']) + '\n Please confirm your details', reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))

    return CONFIRM

def confirm(update,context):
    result = update.message.text
    if result == 'Yes':        
        update.message.reply_text('Thanks for confirming, you may now report beacons using the /report command', reply_markup=ReplyKeyboardRemove())
        return REPORT

    context.user_data.clear()
    update.message.reply_text('ok, lets try again, please send me your callsign', reply_markup=ReplyKeyboardRemove())
    user_id = update.message.chat_id
    print(update.message.chat_id)
    return CALLSIGN


def main():
    pp = PicklePersistence(filename='vhfbeaconbot')
    updater = Updater(TELEGRAMTOKEN, persistence=pp, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # CALLSIGN, LOCATION, CONFIRM, REPORT, BEACON, RST, CONFIRMREPORT
    conv_handler = ConversationHandler( persistent=True, name='cv_persistent',
        entry_points=[CommandHandler('start', start)],

        states={
            CALLSIGN: [MessageHandler(Filters.text, callsign)],

            LOCATION: [MessageHandler(Filters.location, location)],

            CONFIRM: [MessageHandler(Filters.regex('^(Yes|No)$'), confirm)],

            REPORT: [MessageHandler(Filters.text, report),
                    CommandHandler('report', start_beacon_report)],

            BEACON: [MessageHandler(Filters.text, report_beacon)],

            RST: [MessageHandler(Filters.text, report_rst)],

            CONFIRMREPORT: [MessageHandler(Filters.regex('^(Yes|No)$'), confirm_report)],

        },

        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start), CommandHandler('reset', reset)]
        
    )    

    dp.add_handler(conv_handler)    

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()
