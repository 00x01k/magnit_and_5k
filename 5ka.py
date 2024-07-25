import requests
from bs4 import BeautifulSoup
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext

# URLs for Pyaterochka and Magnit
urls = {
    'pyaterochka': 'https://proshoper.ru/actions/pyaterochka/krasnodar/',
    'magnit': 'https://proshoper.ru/actions/magnit-magazin/krasnodar/'
}

# Telegram bot token
TELEGRAM_BOT_TOKEN = '####:####'

# Function to parse and convert price to a number
def parse_price(price_str):
    try:
        return float(re.sub(r'[₽\s,]', '', price_str))
    except ValueError:
        return 0

# Function to format price
def format_price(price_str):
    pattern = re.compile(r'(\d+)(\d{2})₽')
    matches = pattern.findall(price_str)
    formatted_prices = [f"{rubles}.{kopecks} ₽" for rubles, kopecks in matches]
    return " ".join(formatted_prices)

# Function to calculate discount percentage
def calculate_discount_percentage(original_price, discounted_price):
    try:
        original_price = parse_price(original_price)
        discounted_price = parse_price(discounted_price)
        return round(((original_price - discounted_price) / original_price) * 100, 2)
    except ZeroDivisionError:
        return 0

# Function to get discount period
def get_discount_period(soup):
    period_div = soup.find('div', class_='text-sm mt-1')
    return period_div.get_text(strip=True) if period_div else "Период не указан"

# Function to split messages into chunks
def split_message(message: str, max_length: int = 4096) -> list:
    chunks = []
    while len(message) > max_length:
        split_index = message.rfind('\n', 0, max_length)
        if split_index == -1:
            split_index = max_length
        chunks.append(message[:split_index])
        message = message[split_index:].lstrip()
    chunks.append(message)
    return chunks

# Function to get sections from a store URL
def get_sections(url: str) -> dict:
    response = requests.get(url)
    response.raise_for_status()  # Check for errors
    soup = BeautifulSoup(response.text, 'html.parser')

    sections = {}
    for section in soup.find_all('section'):
        section_id = section.get('id')
        if section_id:
            section_name = section.find('span', class_='font-bold md:font-normal').get_text(strip=True) if section.find('span', class_='font-bold md:font-normal') else section_id
            sections[section_id] = section_name

    return sections

# Function to clear all bot messages
async def clear_bot_messages(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id if update.message else update.callback_query.message.chat_id
    if 'bot_messages' in context.user_data:
        for message_id in context.user_data['bot_messages']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                print(f"Failed to delete message {message_id}: {e}")
        context.user_data['bot_messages'] = []

# Function to handle the /start command
async def start(update: Update, context: CallbackContext) -> None:
    query = update.callback_query if update.callback_query else None
    chat_id = query.message.chat_id if query else update.message.chat_id

    await clear_bot_messages(update, context)

    keyboard = [
        [InlineKeyboardButton("5ка", callback_data='pyaterochka')],
        [InlineKeyboardButton("Магнит", callback_data='magnit')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent_message = await context.bot.send_message(chat_id=chat_id, text='Выберите магазин для получения скидок:', reply_markup=reply_markup)
    context.user_data['bot_messages'] = [sent_message.message_id]

# Function to handle store selection
async def handle_store_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    store = query.data
    url = urls.get(store)

    if url:
        sections = get_sections(url)

        if sections:
            await clear_bot_messages(update, context)
            keyboard = [[InlineKeyboardButton(name, callback_data=f'{store}_{section_id}')] for section_id, name in sections.items()]
            keyboard.append([InlineKeyboardButton("Вернуться к выбору магазина", callback_data='back_to_store_selection')])
            reply_markup = InlineKeyboardMarkup(keyboard)

            sent_message = await context.bot.send_message(chat_id=query.message.chat_id, text='Выберите раздел:', reply_markup=reply_markup)
            context.user_data['bot_messages'] = [sent_message.message_id]
            context.user_data['sections'] = sections
            context.user_data['store'] = store
        else:
            await query.message.reply_text('Разделы не найдены.')
            keyboard = [
                [InlineKeyboardButton("Вернуться к выбору магазина", callback_data='back_to_store_selection')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text('Выберите действие:', reply_markup=reply_markup)

# Function to handle section selection
async def handle_section_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data.split('_', 1)
    store = data[0]
    section_id = data[1]

    url = urls.get(store)

    if url:
        try:
            response = requests.get(url)
            response.raise_for_status()  # Check for errors

            soup = BeautifulSoup(response.text, 'html.parser')

            products_in_section = []
            section = soup.find('section', id=section_id)
            if section:
                for product in section.find_all('article', class_='product'):
                    product_id = product.get('id')
                    descr_element = product.find('div', class_='product__descr')
                    price_element = product.find('span', class_='product__price-new')
                    original_price_element = product.find('span', class_='product__price-old')

                    if product_id and product_id.startswith('id_product_'):
                        if descr_element and price_element and original_price_element:
                            description = descr_element.get_text(strip=True)
                            discounted_price = price_element.get_text(strip=True)
                            original_price = original_price_element.get_text(strip=True)

                            formatted_discounted_price = format_price(discounted_price)
                            formatted_original_price = format_price(original_price)

                            price_part = ''.join(re.findall(r'\d+₽\d*₽', description))
                            formatted_price = format_price(price_part)
                            clean_description = re.sub(r'\d+₽\d*₽', '', description).strip()

                            discount_percentage = calculate_discount_percentage(original_price, discounted_price)

                            price_difference = (parse_price(original_price) - parse_price(discounted_price)) / 100
                            formatted_price_difference = f"{price_difference:.2f} ₽"

                            final_description = (f"{clean_description}, Скидка: {formatted_discounted_price} "
                                                 f"(оригинал: {formatted_original_price}, разница: {formatted_price_difference}) "
                                                 f"- {discount_percentage}%")

                            products_in_section.append({
                                'id': product_id,
                                'description': final_description,
                                'discounted_price': formatted_discounted_price,
                                'original_price': formatted_original_price,
                                'discount_percentage': discount_percentage,
                            })

                if products_in_section:
                    top_discounts = sorted(products_in_section, key=lambda x: x['discount_percentage'], reverse=True)
                    message = f"\nПериод действия скидок: {get_discount_period(soup)}\n"
                    message += f"\nРаздел: {context.user_data['sections'].get(section_id, section_id)}\n"
                    for product in top_discounts:
                        message += f"{product['description']}\n\n"

                    message_chunks = split_message(message)

                    await clear_bot_messages(update, context)

                    context.user_data['bot_messages'] = []
                    for chunk in message_chunks:
                        sent_message = await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)
                        context.user_data['bot_messages'].append(sent_message.message_id)

                    keyboard = [
                        [InlineKeyboardButton("Вернуться к выбору магазина", callback_data='back_to_store_selection')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    sent_message = await context.bot.send_message(chat_id=query.message.chat_id, text='Выберите действие:', reply_markup=reply_markup)
                    context.user_data['bot_messages'].append(sent_message.message_id)
                else:
                    await query.message.reply_text('Товары не найдены.')
                    keyboard = [
                        [InlineKeyboardButton("Вернуться к выбору магазина", callback_data='back_to_store_selection')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.message.reply_text('Выберите действие:', reply_markup=reply_markup)
        except requests.RequestException as e:
            await query.message.reply_text(f'Ошибка при запросе данных: {e}')

# Function to handle returning to store selection
async def handle_back_to_store_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    await clear_bot_messages(update, context)

    await start(update, context)

# Main function to run the bot
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(handle_store_selection, pattern='^(pyaterochka|magnit)$'))
    application.add_handler(CallbackQueryHandler(handle_section_selection, pattern='^(pyaterochka|magnit)_.+$'))
    application.add_handler(CallbackQueryHandler(handle_back_to_store_selection, pattern='^back_to_store_selection$'))

    application.run_polling()

if __name__ == '__main__':
    main()
