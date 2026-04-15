import asyncio
import requests
from io import BytesIO
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command, BaseFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery
import json

# Settings
API_TOKEN = ""
ADMIN_ID = 0
ASF_URL = "http://127.0.0.1:1242/Api/ASF"
ASF_PASSWORD = "0"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Classes
class AdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == ADMIN_ID

# Functions
def get_currency_name(currency_id: int) -> str:
    if currency_id == 1:
        return "USD"
    elif currency_id == 3:
        return "EUR"
    elif currency_id == 5:
        return "RUB"
    elif currency_id == 18:
        return "UAH"
    elif currency_id == 6:
        return "PLN"
    elif currency_id == 0:
        return ""
    else:
        return "???"
    
def format_asf(data: dict) -> str:
    result = data.get("Result", {})
    config = result.get("GlobalConfig", {})

    lines = []

    lines.append(f"Версия ASF: {result.get('Version')}")
    can_update = result.get("CanUpdate")
    if result.get("CanUpdate"):
        lines.append("🔄 Доступно обновление")
    memory_kb = result.get("MemoryUsage", 0)
    memory_mb = memory_kb / 1024
    lines.append(f"Используется памяти: {memory_mb:.2f} MB")
    lines.append(f"Работает: {get_uptime(result.get('ProcessStartTime'))}")

    return "\n".join(lines)

def get_uptime(start_time_str: str) -> str:
    # убираем лишнюю точность (Python не любит 7 знаков)
    start_time_str = start_time_str[:26] + "Z"

    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)

    delta = now - start_time

    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{days}д {hours}ч {minutes}м {seconds}с"

def format_bot_ui(bot: dict) -> str:
    # основные статусы
    online = "🟢 Онлайн" if bot.get("IsConnectedAndLoggedOn") else "❌ Оффлайн"
    now_farming = bot.get("CardsFarmer", {}).get("NowFarming")

    if now_farming:
        status_line = "🎮 Фармит: играть нельзя!"
    else:
        status_line = "🎮 Не фармит: можно играть!"

    time = bot.get("CardsFarmer", {}).get("TimeRemaining", "00:00:00")
    games_to_farm = len(bot.get("CardsFarmer", {}).get("GamesToFarm", []))

    twofa = "есть" if bot.get("HasMobileAuthenticator") else "нет"

    # баланс
    balance_raw = bot.get("WalletBalance", 0)
    balance = balance_raw / 100

    currency_id = bot.get("WalletCurrency", 0)
    currency = get_currency_name(currency_id)

    # ключи
    redeem = bot.get("GamesToRedeemInBackgroundCount", 0)

    steam_id = bot.get("SteamID")
    steam_trade_token = bot.get("BotConfig", {}).get("SteamTradeToken")

    text = (
        f"🤖 {bot.get('BotName')} ({bot.get('Nickname')})\n\n"

        f"{online}\n"
        f"{status_line}\n"
        f"Steam id: <code>{steam_id}</code>\n"
        f"Trade Token: <code>{steam_trade_token}</code>\n"
        f"🔐 2FA: {twofa}\n\n"

        f"💰 Баланс: {balance:.2f} {currency}\n"
    )

    # ключи (только если есть)
    if redeem > 0:
        text += f"📦 Ключей в очереди: {redeem}\n"

    # если фармит → показываем время и очередь игр
    if now_farming:
        text += f"\n⏱ Осталось: {time}\n"

        if games_to_farm > 0:
            text += f"📚 В очереди игр: {games_to_farm}\n"

    return text

def get_asf_status_text():
    response = requests.get(
        ASF_URL,
        headers={"Authentication": ASF_PASSWORD}
    )

    if response.status_code != 200:
        return f"Ошибка API: {response.status_code}"

    data = response.json()

    if not data.get("Success"):
        return "ASF вернул ошибку"

    status_text = format_asf(data)
    return f"Панель управления ASF\n\n{status_text}"

def get_2fa_code(bot_name: str) -> str:
    response = requests.get(
        f"http://127.0.0.1:1242/Api/Bot/{bot_name}/TwoFactorAuthentication/Token",
        headers={"Authentication": ASF_PASSWORD}
    )

    if response.status_code != 200:
        return f"Ошибка HTTP {response.status_code}"

    data = response.json()

    if not data.get("Success"):
        return "Ошибка ASF"

    try:
        return data["Result"][bot_name]["Result"]
    except:
        return "Не удалось получить код"
    
def get_farm_summary(bots: dict) -> str:
    total_games = 0
    total_time_seconds = 0

    for bot in bots.values():
        farmer = bot.get("CardsFarmer", {})

        # если бот фармит
        if farmer.get("NowFarming"):
            games = farmer.get("CurrentGamesFarming", [])
            total_games += len(games)

            # время
            time_str = farmer.get("TimeRemaining", "00:00:00")
            h, m, s = map(int, time_str.split(":"))
            total_time_seconds += h * 3600 + m * 60 + s

    # если ничего не фармится
    if total_games == 0:
        return "❌ На аккаунтах нечего не фармиться"

    # перевод времени обратно
    hours = total_time_seconds // 3600
    minutes = (total_time_seconds % 3600) // 60

    return (
        f"🎮 Игр фармится: {total_games}\n"
        f"⏱ Осталось времени: {hours}ч {minutes}м\n"
        f"🃏 Карт осталось: ~{total_games * 3}"  # грубая оценка
    )

def format_bot(bot_data: dict) -> str:
    return json.dumps(bot_data, indent=2, ensure_ascii=False)

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
        [InlineKeyboardButton(text="🤖 Боты", callback_data="bots")]
    ])
def back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])
def bots_keyboard(bots: dict):
    keyboard = []

    for name in bots.keys():
        keyboard.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"bot_{name}"
            )
        ])

    # кнопка назад
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Handlers
@dp.message(Command("start"), AdminFilter())
async def start_handler(message: Message):
    try:
        await message.delete()
    except:
        pass

    try:
        text = get_asf_status_text()

        await message.answer(
            text,
            reply_markup=main_keyboard()
        )

    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.callback_query(lambda c: c.data == "bots")
async def bots_handler(callback: CallbackQuery):
    await callback.answer()

    try:
        response = requests.get(
            "http://127.0.0.1:1242/Api/Bot/ASF",
            headers={"Authentication": ASF_PASSWORD}
        )

        if response.status_code != 200:
            await callback.message.edit_text("Ошибка API")
            return

        data = response.json()

        if not data.get("Success"):
            await callback.message.edit_text("ASF вернул ошибку")
            return

        bots = data.get("Result", {})

        count = len(bots)

        summary = get_farm_summary(bots)

        text = (
            f"🤖 Ботов всего: {count}\n\n"
            f"{summary}\n\n"
            f"Выбери бота:"
        )

        await callback.message.edit_text(
            text,
            reply_markup=bots_keyboard(bots)
        )

    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")

@dp.callback_query(lambda c: c.data.startswith("bot_"))
async def bot_selected(callback: CallbackQuery):
    await callback.answer()

    bot_name = callback.data.replace("bot_", "")

    try:
        response = requests.get(
            "http://127.0.0.1:1242/Api/Bot/ASF",
            headers={"Authentication": ASF_PASSWORD}
        )

        data = response.json()
        bots = data.get("Result", {})

        bot = bots.get(bot_name)

        if not bot:
            await callback.message.edit_text("Бот не найден")
            return

        text = format_bot_ui(bot)

        await callback.message.edit_text(
    text,
    parse_mode="HTML",
    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 2FA", callback_data=f"2fa_{bot_name}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="bots")]
    ])
)

    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")

@dp.callback_query(lambda c: c.data == "back")
async def back_button(callback: CallbackQuery):
    await callback.answer()

    try:
        text = get_asf_status_text()

        await callback.message.edit_text(
            text,
            reply_markup=main_keyboard()
        )

    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")

@dp.callback_query(lambda c: c.data == "refresh")
async def refresh_handler(callback: CallbackQuery):
    await callback.answer()

    try:
        text = get_asf_status_text()

        await callback.message.edit_text(
            text,
            reply_markup=main_keyboard()
        )

    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")

@dp.callback_query(lambda c: c.data.startswith("2fa_") and not c.data.startswith("2fa_refresh_"))
async def twofa_handler(callback: CallbackQuery):
    await callback.answer()

    bot_name = callback.data.replace("2fa_", "")

    try:
        code = get_2fa_code(bot_name)

        text = (
            f"🤖 {bot_name}\n\n"
            f"<code>{code}</code>"
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить код", callback_data=f"2fa_refresh_{bot_name}")],
                [InlineKeyboardButton(
    text="⬅️ Назад",
    callback_data=f"bot_{bot_name}"
)]
            ])
        )

    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")

@dp.callback_query(lambda c: c.data.startswith("2fa_refresh_"))
async def twofa_refresh(callback: CallbackQuery):
    await callback.answer()

    bot_name = callback.data.replace("2fa_refresh_", "")

    try:
        code = get_2fa_code(bot_name)

        # 🔥 проверяем есть ли уже этот код в тексте
        if callback.message.text and code in callback.message.text:
            await callback.answer("Код ещё не обновился")
            return

        new_text = (
            f"🤖 {bot_name}\n\n"
            f"<code>{code}</code>"
        )

        await callback.message.edit_text(
            new_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить код", callback_data=f"2fa_refresh_{bot_name}")],
                [InlineKeyboardButton(
    text="⬅️ Назад",
    callback_data=f"bot_{bot_name}"
)]
            ])
        )

    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")

# Start
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
