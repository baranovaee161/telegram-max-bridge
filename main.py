import os
import html
import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import (
    init_db,
    add_ad,
    add_report,
    get_ads_by_category,
    delete_ad,
    get_all_ads,
    get_user_ads,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= НАСТРОЙКИ (берутся из переменных окружения Render) =============

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задана переменная окружения BOT_TOKEN")

ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# Render сам подставляет RENDER_EXTERNAL_URL, вручную вписывать адрес не нужно
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")

# Секрет для защиты вебхука, вычисляется из токена
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:32]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())


# ============= СОСТОЯНИЯ =============

class AdStates(StatesGroup):
    writing_title = State()
    writing_description = State()
    writing_price = State()


class AdminStates(StatesGroup):
    waiting_for_ad_id = State()


CATEGORY_NAMES = {
    "electronics": "📱 Электроника",
    "clothing": "👕 Одежда",
    "furniture": "🪑 Мебель",
    "services": "🔧 Услуги",
    "auto": "🚗 Авто",
    "other": "📦 Прочее",
}


# ============= ПОМОЩНИКИ =============

def esc(value) -> str:
    """Экранирует текст, чтобы он не ломал форматирование."""
    return html.escape(str(value))


def contact_url(username: str) -> str:
    if username.startswith("user") and username[4:].isdigit():
        return f"tg://user?id={username[4:]}"
    return f"https://t.me/{username}"


def author_link(username: str) -> str:
    if username.startswith("user") and username[4:].isdigit():
        label = "автор"
    else:
        label = f"@{esc(username)}"
    return f'<a href="{contact_url(username)}">{label}</a>'


def fmt_date(ad) -> str:
    try:
        return ad["created_at"].strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(ad.get("created_at", ""))


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Разместить объявление", callback_data="place_ad")],
        [InlineKeyboardButton(text="🔍 Смотреть объявления", callback_data="view_ads")],
        [InlineKeyboardButton(text="📌 Мои объявления", callback_data="my_ads")],
        [InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")],
    ])


def public_ad_text(ad, header: str = "") -> str:
    text = f"{header}\n\n" if header else ""
    text += (
        f"<b>{esc(ad['title'])}</b>\n"
        f"💰 {esc(ad['price'])}\n\n"
        f"{esc(ad['description'])}\n\n"
        f"<b>Автор:</b> {author_link(ad['username'])}\n"
        f"📅 {fmt_date(ad)}"
    )
    return text


def public_ad_keyboard(ad, next_ad=None) -> InlineKeyboardMarkup:
    rows = []
    if next_ad:
        rows.append([InlineKeyboardButton(text="➡️ Следующее", callback_data=f"ad_{next_ad['id']}")])
    rows.append([
        InlineKeyboardButton(text="💬 Написать", url=contact_url(ad["username"])),
        InlineKeyboardButton(text="❌ Пожаловаться", callback_data=f"report_{ad['id']}"),
    ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="view_ads")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_ad_text(ad, count=None) -> str:
    header = f"<b>📌 Мои объявления</b> ({count})\n\n" if count else ""
    return (
        f"{header}"
        f"<b>{esc(ad['title'])}</b>\n"
        f"💰 {esc(ad['price'])}\n\n"
        f"{esc(ad['description'])}\n\n"
        f"📅 {fmt_date(ad)}"
    )


def my_ad_keyboard(ad, next_ad=None) -> InlineKeyboardMarkup:
    rows = []
    if next_ad:
        rows.append([InlineKeyboardButton(text="➡️ Следующее", callback_data=f"myad_{next_ad['id']}")])
    rows.append([InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{ad['id']}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def next_in_list(ads, ad_id):
    for i, a in enumerate(ads):
        if a["id"] == ad_id:
            return ads[i + 1] if i + 1 < len(ads) else None
    return None


# ============= ГЛАВНОЕ МЕНЮ =============

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в <b>Доска объявлений</b>!\n\n"
        "Здесь вы можете:\n"
        "• 📝 Разместить своё объявление\n"
        "• 🔍 Посмотреть объявления других\n"
        "• ❤️ Найти то, что вам нужно\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "👋 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


# ============= РАЗМЕЩЕНИЕ ОБЪЯВЛЕНИЯ =============

@dp.callback_query(F.data == "place_ad")
async def place_ad_start(callback: types.CallbackQuery):
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"cat_{key}")]
        for key, name in CATEGORY_NAMES.items()
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])
    await callback.message.edit_text(
        "Выберите категорию для вашего объявления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("cat_"))
async def category_selected(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category)
    await state.set_state(AdStates.writing_title)
    await callback.message.edit_text(
        f"📝 Вы выбрали категорию: {CATEGORY_NAMES.get(category, esc(category))}\n\n"
        f"Теперь напишите <b>название</b> вашего объявления (максимум 100 символов):"
    )
    await callback.answer()


@dp.message(AdStates.writing_title, F.text)
async def title_input(message: types.Message, state: FSMContext):
    if len(message.text) > 100:
        await message.answer("❌ Название слишком длинное! Максимум 100 символов. Попробуйте ещё раз:")
        return
    await state.update_data(title=message.text)
    await state.set_state(AdStates.writing_description)
    await message.answer("Отлично! Теперь напишите <b>описание</b> вашего товара или услуги:")


@dp.message(AdStates.writing_description, F.text)
async def description_input(message: types.Message, state: FSMContext):
    if len(message.text) > 500:
        await message.answer("❌ Описание слишком длинное! Максимум 500 символов. Попробуйте ещё раз:")
        return
    await state.update_data(description=message.text)
    await state.set_state(AdStates.writing_price)
    await message.answer("Спасибо! Укажите <b>цену</b> (или напишите 'бесплатно' / 'договорная'):")


@dp.message(AdStates.writing_price, F.text)
async def price_input(message: types.Message, state: FSMContext):
    username = message.from_user.username or f"user{message.from_user.id}"
    await state.update_data(price=message.text, contact=username)
    data = await state.get_data()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Разместить", callback_data="confirm_ad")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_ad")],
    ])
    await message.answer(
        f"📋 <b>Предпросмотр вашего объявления:</b>\n\n"
        f"<b>Название:</b> {esc(data['title'])}\n"
        f"<b>Категория:</b> {CATEGORY_NAMES.get(data['category'], esc(data['category']))}\n"
        f"<b>Описание:</b> {esc(data['description'])}\n"
        f"<b>Цена:</b> {esc(data['price'])}\n"
        f"<b>Автор:</b> {author_link(username)}\n\n"
        f"Всё верно?",
        reply_markup=keyboard,
    )
    await state.set_state(None)


@dp.callback_query(F.data == "confirm_ad")
async def confirm_ad(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("title"):
        await callback.message.edit_text("❌ Данные объявления потерялись. Начните заново через /start")
        await callback.answer()
        return

    username = callback.from_user.username or f"user{callback.from_user.id}"
    try:
        ad_id = await add_ad(
            user_id=callback.from_user.id,
            username=username,
            category=data["category"],
            title=data["title"],
            description=data["description"],
            price=data["price"],
        )
        await callback.message.edit_text(
            f"✅ <b>Объявление размещено!</b>\n\n"
            f"ID вашего объявления: <code>{ad_id}</code>\n\n"
            f"Его смогут увидеть другие пользователи в разделе "
            f"«{CATEGORY_NAMES.get(data['category'], esc(data['category']))}»"
        )
    except Exception as e:
        logger.error(f"Error adding ad: {e}")
        await callback.message.edit_text("❌ Ошибка при размещении объявления. Попробуйте ещё раз позже.")

    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "cancel_ad")
async def cancel_ad(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Размещение отменено.")
    await callback.answer()


# ============= ПРОСМОТР ОБЪЯВЛЕНИЙ =============

@dp.callback_query(F.data == "view_ads")
async def view_ads_menu(callback: types.CallbackQuery):
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"view_{key}")]
        for key, name in CATEGORY_NAMES.items()
    ]
    rows.append([InlineKeyboardButton(text="🌐 Все объявления", callback_data="view_all")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])
    await callback.message.edit_text(
        "Выберите категорию для просмотра:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("view_"))
async def view_category_ads(callback: types.CallbackQuery):
    category = callback.data.replace("view_", "")
    try:
        if category == "all":
            ads = await get_all_ads()
            title = "🌐 <b>Все объявления</b>"
        else:
            ads = await get_ads_by_category(category)
            title = f"<b>{CATEGORY_NAMES.get(category, esc(category))}</b>"

        if not ads:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="view_ads")]
            ])
            await callback.message.edit_text(f"{title}\n\n❌ Объявлений нет.", reply_markup=keyboard)
            await callback.answer()
            return

        ad = ads[0]
        next_ad = ads[1] if len(ads) > 1 else None
        await callback.message.edit_text(
            public_ad_text(ad, title),
            reply_markup=public_ad_keyboard(ad, next_ad),
        )
    except Exception as e:
        logger.error(f"Error viewing ads: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке объявлений.")
    await callback.answer()


@dp.callback_query(F.data.startswith("ad_"))
async def view_specific_ad(callback: types.CallbackQuery):
    try:
        ad_id = int(callback.data.replace("ad_", ""))
        ads = await get_all_ads()
        ad = next((a for a in ads if a["id"] == ad_id), None)
        if not ad:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        await callback.message.edit_text(
            public_ad_text(ad),
            reply_markup=public_ad_keyboard(ad, next_in_list(ads, ad_id)),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error viewing ad: {e}")
        await callback.answer("❌ Ошибка при загрузке объявления", show_alert=True)


@dp.callback_query(F.data.startswith("report_"))
async def report_ad(callback: types.CallbackQuery):
    ad_id_text = callback.data.replace("report_", "")
    try:
        await add_report(int(ad_id_text), callback.from_user.id)
    except Exception as e:
        logger.warning(f"Could not save report: {e}")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"⚠️ Жалоба на объявление #{esc(ad_id_text)}\n"
                f"От пользователя: {callback.from_user.id}",
            )
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")
    await callback.answer("Спасибо! Жалоба отправлена администратору.", show_alert=True)


# ============= МОИ ОБЪЯВЛЕНИЯ =============

@dp.callback_query(F.data == "my_ads")
async def my_ads(callback: types.CallbackQuery):
    try:
        ads = await get_user_ads(callback.from_user.id)

        if not ads:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Разместить объявление", callback_data="place_ad")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
            ])
            await callback.message.edit_text("📭 У вас пока нет объявлений.", reply_markup=keyboard)
            await callback.answer()
            return

        ad = ads[0]
        next_ad = ads[1] if len(ads) > 1 else None
        await callback.message.edit_text(
            my_ad_text(ad, len(ads)),
            reply_markup=my_ad_keyboard(ad, next_ad),
        )
    except Exception as e:
        logger.error(f"Error getting user ads: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке ваших объявлений.")
    await callback.answer()


@dp.callback_query(F.data.startswith("myad_"))
async def view_specific_user_ad(callback: types.CallbackQuery):
    try:
        ad_id = int(callback.data.replace("myad_", ""))
        ads = await get_user_ads(callback.from_user.id)
        ad = next((a for a in ads if a["id"] == ad_id), None)
        if not ad:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        await callback.message.edit_text(
            my_ad_text(ad),
            reply_markup=my_ad_keyboard(ad, next_in_list(ads, ad_id)),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error viewing user ad: {e}")
        await callback.answer("❌ Ошибка при загрузке объявления", show_alert=True)


@dp.callback_query(F.data.startswith("delete_"))
async def delete_ad_confirm(callback: types.CallbackQuery):
    ad_id = int(callback.data.replace("delete_", ""))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{ad_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="my_ads"),
        ]
    ])
    await callback.message.edit_text(
        "⚠️ Вы уверены? Удалённое объявление нельзя восстановить.",
        reply_markup=keyboard,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_ad(callback: types.CallbackQuery):
    ad_id = int(callback.data.replace("confirm_delete_", ""))
    try:
        ok = await delete_ad(ad_id, callback.from_user.id)
        if ok:
            await callback.message.edit_text("✅ Объявление удалено.")
        else:
            await callback.message.edit_text("❌ Не удалось удалить объявление.")
    except Exception as e:
        logger.error(f"Error deleting ad: {e}")
        await callback.message.edit_text("❌ Ошибка при удалении объявления.")
    await callback.answer()


# ============= АДМИН-ПАНЕЛЬ =============

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ У вас нет доступа к админ-панели", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить объявление", callback_data="admin_delete")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
    ])
    await callback.message.edit_text("⚙️ <b>Админ-панель</b>", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "admin_delete")
async def admin_delete_ad(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_ad_id)
    await callback.message.edit_text("Введите ID объявления для удаления:")
    await callback.answer()


@dp.message(AdminStates.waiting_for_ad_id, F.text)
async def admin_delete_confirm(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    try:
        ad_id = int(message.text.strip())
        ok = await delete_ad(ad_id)
        if ok:
            await message.answer(f"✅ Объявление #{ad_id} удалено.")
        else:
            await message.answer("❌ Не удалось удалить объявление.")
    except ValueError:
        await message.answer("❌ Введите корректный ID объявления (число).")
        return
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer("❌ Ошибка при удалении.")
    await state.clear()


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    try:
        all_ads = await get_all_ads()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")]
        ])
        await callback.message.edit_text(
            f"📊 <b>Статистика</b>\n\n📌 Всего объявлений: {len(all_ads)}",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке статистики.")
    await callback.answer()


# ============= ЗАПУСК (WEBHOOK) =============

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    if WEBHOOK_URL:
        try:
            await bot.set_webhook(f"{WEBHOOK_URL}/webhook", secret_token=WEBHOOK_SECRET)
            logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    else:
        logger.error("Не найден адрес сервиса (WEBHOOK_URL / RENDER_EXTERNAL_URL). Webhook не установлен!")

    yield

    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    update = types.Update.model_validate(await request.json(), context={"bot": bot})
    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Error while handling update")
    return PlainTextResponse("ok")


@app.api_route("/", methods=["GET", "HEAD"])
async def index():
    return PlainTextResponse("Bot is running!")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
