import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
import firebase_admin
from firebase_admin import credentials, firestore

# Firebase setup
cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
if not cred_json:
    raise ValueError("FIREBASE_CREDENTIALS_JSON environment variable not set.")

cred = credentials.Certificate(json.loads(cred_json))
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://myid-9e87b-default-rtdb.asia-southeast1.firebasedatabase.app'
})
db = firestore.client()

# List of admin IDs
ADMIN_IDS = ["5084989466", "987654321"]  # Replace with actual Telegram user IDs of admins

# Verify admin
def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

# Start command
def start(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username

    user_ref = db.collection('users').document(user_id)
    user = user_ref.get()

    if not user.exists:
        user_ref.set({
            'username': username,
            'balance': 0
        })
        update.message.reply_text(f"Account created for {username}. Balance: 0")
    else:
        user_data = user.to_dict()
        update.message.reply_text(f"Welcome back, {username}! Balance: {user_data['balance']}")

    if is_admin(user_id):
        show_admin_menu(update, context)
    else:
        show_main_menu(update, context)

# Show main menu for users
def show_main_menu(update: Update, context: CallbackContext):
    games_ref = db.collection('games')
    games = games_ref.stream()

    keyboard = [[InlineKeyboardButton(game.to_dict()['name'], callback_data=f"game_{game.id}")] for game in games]

    update.message.reply_text("Choose a game:", reply_markup=InlineKeyboardMarkup(keyboard))

# Show admin menu
def show_admin_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("View Users", callback_data="admin_view_users")],
        [InlineKeyboardButton("Recharge User", callback_data="admin_recharge_user")],
        [InlineKeyboardButton("Add Game", callback_data="admin_add_game")],
        [InlineKeyboardButton("Add Item", callback_data="admin_add_item")],
        [InlineKeyboardButton("Update Item", callback_data="admin_update_item")],
        [InlineKeyboardButton("View Orders", callback_data="admin_view_orders")]
    ]

    update.message.reply_text("Admin Menu:", reply_markup=InlineKeyboardMarkup(keyboard))

# Handle game selection
def game_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    game_id = query.data.split('_')[1]

    items_ref = db.collection('items').where('game_id', '==', game_id)
    items = items_ref.stream()

    keyboard = [[InlineKeyboardButton(f"{item.to_dict()['name']} - {item.to_dict()['price']} coins", callback_data=f"item_{item.id}_{game_id}")] for item in items]

    query.edit_message_text("Select an item:", reply_markup=InlineKeyboardMarkup(keyboard))

# Handle item selection
def item_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    item_id, game_id = query.data.split('_')[1:]

    context.user_data['item_id'] = item_id
    context.user_data['game_id'] = game_id

    query.edit_message_text("Enter your game ID:")

# Handle game ID input
def game_id_input(update: Update, context: CallbackContext):
    game_id = context.user_data.get('game_id')
    item_id = context.user_data.get('item_id')
    user_id = str(update.effective_user.id)
    game_user_id = update.message.text

    item_ref = db.collection('items').document(item_id)
    item = item_ref.get().to_dict()

    user_ref = db.collection('users').document(user_id)
    user = user_ref.get().to_dict()

    if user['balance'] >= item['price']:
        new_balance = user['balance'] - item['price']
        user_ref.update({'balance': new_balance})

        db.collection('transactions').add({
            'user_id': user_id,
            'item_id': item_id,
            'game_id': game_id,
            'amount': item['price'],
            'status': 'completed',
            'game_user_id': game_user_id
        })

        update.message.reply_text(f"Purchase successful! {item['name']} bought for {item['price']} coins. Remaining balance: {new_balance}")
    else:
        update.message.reply_text("Insufficient balance!")

# Admin commands
# Get all users
def get_all_users():
    users_ref = db.collection('users')
    users = users_ref.stream()
    return [user.to_dict() for user in users]

# Recharge user
def recharge_user(user_id, amount):
    user_ref = db.collection('users').document(user_id)
    user = user_ref.get()
    if user.exists:
        new_balance = user.to_dict()['balance'] + amount
        user_ref.update({'balance': new_balance})
        return True
    return False

# Add game
def add_game(game_name):
    db.collection('games').add({'name': game_name})

# Add item
def add_item(game_id, item_name, price):
    db.collection('items').add({
        'game_id': game_id,
        'name': item_name,
        'price': price
    })

# Update item info
def update_item(item_id, new_name=None, new_price=None):
    item_ref = db.collection('items').document(item_id)
    updates = {}
    if new_name:
        updates['name'] = new_name
    if new_price:
        updates['price'] = new_price
    if updates:
        item_ref.update(updates)

# View orders
def view_orders():
    transactions_ref = db.collection('transactions')
    transactions = transactions_ref.stream()
    return [trans.to_dict() for trans in transactions]

# Admin command wrapper
def admin_only(func):
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = str(update.effective_user.id)
        if not is_admin(user_id):
            update.message.reply_text("Unauthorized access. Admins only.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

# Main function
def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set.")

    updater = Updater(bot_token)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(game_selected, pattern="^game_"))
    dispatcher.add_handler(CallbackQueryHandler(item_selected, pattern="^item_"))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, game_id_input))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
