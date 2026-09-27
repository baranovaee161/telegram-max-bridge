import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
import asyncio
from dotenv import load_dotenv

from database import init_db, add_ad, get_ads_by_category, delete_ad, get_all_ads, get_user_ads, ban_user, is_admin, add_admin

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем значения из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []
DATABASE_URL = os.getenv('DATABASE_URL')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-app.onrender.com')

# Инициализируем FastAPI
app = FastAPI()

# Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для FSM (конечный автомат)
class AdStates(StatesGroup):
    choosing_category = State()
    writing_title = State()
    writing_description = State()
    writing_price = State()
    writing_contact = State()

class AdminStates(StatesGroup):
    waiting_for_ad_id = State()
    waiting_for_reason = State()

CATEGORIES = {
    'электроника': 'electronics',
    'одежда': 'clothing',
    'мебель': 'furniture',
    'услуги': 'services',
    'авто': 'auto',
    'прочее': 'other'
}

CATEGORY_NAMES = {
    'electronics': '📱 Электроника',
    'clothing': '👕 Одежда',
    'furniture': '🪑 Мебель',
    'services': '🔧 Услуги',
    'auto': '🚗 Авто',
    'other': '📦 Прочее'
}

# ============= ГЛАВНОЕ МЕНЮ =============

@dp.message(CommandStart())
async def start(message: types.Message):
    """Главное меню бота"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Разместить объявление", callback_data="place_ad")],
        [InlineKeyboardButton(text="🔍 Смотреть объявления", callback_data="view_ads")],
        [InlineKeyboardButton(text="📌 Мои объявления", callback_data="my_ads")],
        [InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")],
    ])
    
    await message.answer(
        "👋 Добро пожаловать в **Доска объявлений**!\n\n"
        "Здесь вы можете:\n"
        "• 📝 Разместить своё объявление\n"
        "• 🔍 Посмотреть объявления других\n"
        "• ❤️ Найти то, что вам нужно\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ============= РАЗМЕЩЕНИЕ ОБЪЯВЛЕНИЯ =============

@dp.callback_query(F.data == "place_ad")
async def place_ad_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало размещения объявления - выбор категории"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Электроника", callback_data="cat_electronics")],
        [InlineKeyboardButton(text="👕 Одежда", callback_data="cat_clothing")],
        [InlineKeyboardButton(text="🪑 Мебель", callback_data="cat_furniture")],
        [InlineKeyboardButton(text="🔧 Услуги", callback_data="cat_services")],
        [InlineKeyboardButton(text="🚗 Авто", callback_data="cat_auto")],
        [InlineKeyboardButton(text="📦 Прочее", callback_data="cat_other")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
    ])
    
    await callback.message.edit_text(
        "Выберите категорию для вашего объявления:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("cat_"))
async def category_selected(callback: types.CallbackQuery, state: FSMContext):
    """Категория выбрана, начинаем заполнение объявления"""
    category = callback.data.replace("cat_", "")
    
    await state.update_data(category=category)
    await state.set_state(AdStates.writing_title)
    
    await callback.message.edit_text(
        f"📝 Вы выбрали категорию: {CATEGORY_NAMES.get(category, category)}\n\n"
        f"Теперь напишите **название** вашего объявления (максимум 100 символов):",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(AdStates.writing_title)
async def title_input(message: types.Message, state: FSMContext):
    """Получаем название объявления"""
    if len(message.text) > 100:
        await message.answer("❌ Название слишком длинное! Максимум 100 символов. Попробуйте ещё раз:")
        return
    
    await state.update_data(title=message.text)
    await state.set_state(AdStates.writing_description)
    
    await message.answer(
        "Отлично! Теперь напишите **описание** вашего товара или услуги:"
    )

@dp.message(AdStates.writing_description)
async def description_input(message: types.Message, state: FSMContext):
    """Получаем описание"""
    if len(message.text) > 500:
        await message.answer("❌ Описание слишком длинное! Максимум 500 символов. Попробуйте ещё раз:")
        return
    
    await state.update_data(description=message.text)
    await state.set_state(AdStates.writing_price)
    
    await message.answer(
        "Спасибо! Укажите **цену** (или напишите 'бесплатно'/'договорная'):"
    )

@dp.message(AdStates.writing_price)
async def price_input(message: types.Message, state: FSMContext):
    """Получаем цену"""
    await state.update_data(price=message.text)
    
    # Получаем никнейм пользователя
    user = await bot.get_chat(message.from_user.id)
    username = user.username if user.username else f"user{message.from_user.id}"
    
    await state.update_data(contact=username)
    
    # Подтверждение данных перед размещением
    data = await state.get_data()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Разместить", callback_data="confirm_ad")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_ad")],
    ])
    
    ad_text = (
        f"📋 **Предпросмотр вашего объявления:**\n\n"
        f"**Название:** {data['title']}\n"
        f"**Категория:** {CATEGORY_NAMES.get(data['category'], data['category'])}\n"
        f"**Описание:** {data['description']}\n"
        f"**Цена:** {data['price']}\n"
        f"**Автор:** @{username}\n\n"
        f"Всё верно?"
    )
    
    await message.answer(ad_text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(None)

@dp.callback_query(F.data == "confirm_ad")
async def confirm_ad(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение и размещение объявления"""
    data = await state.get_data()
    
    user = await bot.get_chat(callback.from_user.id)
    username = user.username if user.username else f"user{callback.from_user.id}"
    
    # Сохраняем в БД
    try:
        ad_id = await add_ad(
            user_id=callback.from_user.id,
            username=username,
            category=data['category'],
            title=data['title'],
            description=data['description'],
            price=data['price']
        )
        
        await callback.message.edit_text(
            f"✅ **Объявление размещено!**\n\n"
            f"ID вашего объявления: `{ad_id}`\n\n"
            f"Его смогут увидеть другие пользователи в разделе '{CATEGORY_NAMES.get(data['category'], data['category'])}'",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error adding ad: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при размещении объявления. Попробуйте ещё раз позже."
        )
    
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "cancel_ad")
async def cancel_ad(callback: types.CallbackQuery, state: FSMContext):
    """Отмена размещения"""
    await state.clear()
    await callback.message.edit_text("❌ Размещение отменено.")
    await callback.answer()

# ============= ПРОСМОТР ОБЪЯВЛЕНИЙ =============

@dp.callback_query(F.data == "view_ads")
async def view_ads_menu(callback: types.CallbackQuery):
    """Меню просмотра объявлений - выбор категории"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Электроника", callback_data="view_electronics")],
        [InlineKeyboardButton(text="👕 Одежда", callback_data="view_clothing")],
        [InlineKeyboardButton(text="🪑 Мебель", callback_data="view_furniture")],
        [InlineKeyboardButton(text="🔧 Услуги", callback_data="view_services")],
        [InlineKeyboardButton(text="🚗 Авто", callback_data="view_auto")],
        [InlineKeyboardButton(text="📦 Прочее", callback_data="view_other")],
        [InlineKeyboardButton(text="🌐 Все объявления", callback_data="view_all")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
    ])
    
    await callback.message.edit_text(
        "Выберите категорию для просмотра:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("view_"))
async def view_category_ads(callback: types.CallbackQuery):
    """Просмотр объявлений по категории"""
    category = callback.data.replace("view_", "")
    
    try:
        if category == "all":
            ads = await get_all_ads()
            title = "🌐 **Все объявления**"
        else:
            ads = await get_ads_by_category(category)
            title = f"**{CATEGORY_NAMES.get(category, category)}**"
        
        if not ads:
            await callback.message.edit_text(
                f"{title}\n\n❌ Объявлений нет.",
                parse_mode="Markdown"
            )
            await callback.answer()
            return
        
        # Показываем первое объявление
        ad = ads[0]
        
        # Создаём кнопки для навигации
        keyboard_buttons = []
        
        if len(ads) > 1:
            keyboard_buttons.append([
                InlineKeyboardButton(text="➡️ Следующее", callback_data=f"ad_{ads[1]['id']}")
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="💬 Написать", url=f"https://t.me/{ad['username']}"),
            InlineKeyboardButton(text="❌ Пожаловаться", callback_data=f"report_{ad['id']}")
        ])
        keyboard_buttons.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data="view_ads")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        ad_text = (
            f"{title}\n\n"
            f"**{ad['title']}**\n"
            f"💰 {ad['price']}\n\n"
            f"{ad['description']}\n\n"
            f"**Автор:** [@{ad['username']}](https://t.me/{ad['username']})\n"
            f"📅 {ad['created_at'].strftime('%d.%m.%Y %H:%M')}"
        )
        
        await callback.message.edit_text(
            ad_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error viewing ads: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке объявлений.")
    
    await callback.answer()

@dp.callback_query(F.data.startswith("ad_"))
async def view_specific_ad(callback: types.CallbackQuery):
    """Просмотр конкретного объявления"""
    ad_id = int(callback.data.replace("ad_", ""))
    
    try:
        ads = await get_all_ads()
        ad = next((a for a in ads if a['id'] == ad_id), None)
        
        if not ad:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 Написать", url=f"https://t.me/{ad['username']}"),
                InlineKeyboardButton(text="❌ Пожаловаться", callback_data=f"report_{ad['id']}")
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="view_ads")]
        ])
        
        ad_text = (
            f"**{ad['title']}**\n"
            f"💰 {ad['price']}\n\n"
            f"{ad['description']}\n\n"
            f"**Автор:** [@{ad['username']}](https://t.me/{ad['username']})\n"
            f"📅 {ad['created_at'].strftime('%d.%m.%Y %H:%M')}"
        )
        
        await callback.message.edit_text(
            ad_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error viewing ad: {e}")
        await callback.answer("❌ Ошибка при загрузке объявления", show_alert=True)

# ============= МОИ ОБЪЯВЛЕНИЯ =============

@dp.callback_query(F.data == "my_ads")
async def my_ads(callback: types.CallbackQuery):
    """Просмотр объявлений пользователя"""
    try:
        ads = await get_user_ads(callback.from_user.id)
        
        if not ads:
            await callback.message.edit_text(
                "📭 У вас пока нет объявлений.\n\n"
                "[Разместить новое](https://t.me/vsev1dmd_bot?start=place_ad)",
                parse_mode="Markdown"
            )
            await callback.answer()
            return
        
        # Показываем первое объявление
        ad = ads[0]
        
        keyboard_buttons = []
        
        if len(ads) > 1:
            keyboard_buttons.append([
                InlineKeyboardButton(text="➡️ Следующее", callback_data=f"myad_{ads[1]['id']}")
            ])
        
        keyboard_buttons.extend([
            [
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{ad['id']}"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        ad_text = (
            f"**📌 Мои объявления** ({len(ads)})\n\n"
            f"**{ad['title']}**\n"
            f"💰 {ad['price']}\n\n"
            f"{ad['description']}\n\n"
            f"📅 {ad['created_at'].strftime('%d.%m.%Y %H:%M')}"
        )
        
        await callback.message.edit_text(ad_text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error getting user ads: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке ваших объявлений.")
    
    await callback.answer()

@dp.callback_query(F.data.startswith("myad_"))
async def view_specific_user_ad(callback: types.CallbackQuery):
    """Просмотр конкретного объявления пользователя"""
    ad_id = int(callback.data.replace("myad_", ""))
    
    try:
        ads = await get_user_ads(callback.from_user.id)
        ad = next((a for a in ads if a['id'] == ad_id), None)
        
        if not ad:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{ad['id']}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="my_ads")]
        ])
        
        ad_text = (
            f"**{ad['title']}**\n"
            f"💰 {ad['price']}\n\n"
            f"{ad['description']}\n\n"
            f"📅 {ad['created_at'].strftime('%d.%m.%Y %H:%M')}"
        )
        
        await callback.message.edit_text(ad_text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error viewing user ad: {e}")
        await callback.answer("❌ Ошибка при загрузке объявления", show_alert=True)

@dp.callback_query(F.data.startswith("delete_"))
async def delete_ad_confirm(callback: types.CallbackQuery):
    """Подтверждение удаления объявления"""
    ad_id = int(callback.data.replace("delete_", ""))
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{ad_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="my_ads")
        ]
    ])
    
    await callback.message.edit_text(
        "⚠️ Вы уверены? Удалённое объявление нельзя восстановить.",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_ad(callback: types.CallbackQuery):
    """Удаление объявления"""
    ad_id = int(callback.data.replace("confirm_delete_", ""))
    
    try:
        await delete_ad(ad_id, callback.from_user.id)
        await callback.message.edit_text("✅ Объявление удалено.")
    except Exception as e:
        logger.error(f"Error deleting ad: {e}")
        await callback.message.edit_text("❌ Ошибка при удалении объявления.")
    
    await callback.answer()

# ============= АДМИН-ПАНЕЛЬ =============

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    """Админ-панель (только для админов)"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ У вас нет доступа к админ-панели", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить объявление", callback_data="admin_delete")],
        [InlineKeyboardButton(text="🚫 Заблокировать пользователя", callback_data="admin_ban")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
    ])
    
    await callback.message.edit_text(
        "⚙️ **Админ-панель**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_delete")
async def admin_delete_ad(callback: types.CallbackQuery, state: FSMContext):
    """Админ удаляет объявление"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_ad_id)
    await callback.message.edit_text(
        "Введите ID объявления для удаления:"
    )
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad_id)
async def admin_delete_confirm(message: types.Message, state: FSMContext):
    """Подтверждение удаления админом"""
    try:
        ad_id = int(message.text)
        await delete_ad(ad_id)
        await message.answer(f"✅ Объявление #{ad_id} удалено.")
    except ValueError:
        await message.answer("❌ Введите корректный ID объявления (число).")
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer("❌ Ошибка при удалении.")
    
    await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    """Статистика"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    try:
        all_ads = await get_all_ads()
        stats_text = (
            "📊 **Статистика**\n\n"
            f"📌 Всего объявлений: {len(all_ads)}\n"
        )
        
        await callback.message.edit_text(stats_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке статистики.")
    
    await callback.answer()

# ============= НАЗАД В МЕНЮ =============

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    """Возвращаемся в главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Разместить объявление", callback_data="place_ad")],
        [InlineKeyboardButton(text="🔍 Смотреть объявления", callback_data="view_ads")],
        [InlineKeyboardButton(text="📌 Мои объявления", callback_data="my_ads")],
        [InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")],
    ])
    
    await callback.message.edit_text(
        "👋 **Главное меню**\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

# ============= WEBHOOK ENDPOINTS =============

@app.post("/webhook")
async def webhook(request: Request):
    """Webhook endpoint для получения обновлений от Telegram"""
    update_data = await request.json()
    update = types.Update(**update_data)
    await dp.feed_update(bot, update)
    return PlainTextResponse("ok")

@app.get("/")
async def index():
    """Health check endpoint"""
    return PlainTextResponse("Bot is running!")

# ============= ЗАПУСК =============

async def on_startup():
    """Инициализация при запуске"""
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    
    # Установка webhook
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to {webhook_url}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")

async def on_shutdown():
    """Очистка при завершении"""
    await bot.session.close()

# Регистрируем обработчики жизненного цикла
app.add_event_handler("startup", on_startup)
app.add_event_handler("shutdown", on_shutdown)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
