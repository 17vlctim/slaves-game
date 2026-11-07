import asyncio
import time
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# --- НАСТРОЙКИ ---
# Берем токен из настроек Render, чтобы он не светился в GitHub
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Ссылка на твой сервис на Render (без слэша на конце)
WEB_URL = "https://slaves-game.onrender.com" 
PORT = int(os.environ.get("PORT", 8080))

if not BOT_TOKEN:
    raise ValueError("Токен BOT_TOKEN не найден в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (В ПАМЯТИ) ---
users = {}

# --- ЛОГИКА БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    
    # Передаем ID и имя в ссылку, чтобы приложение знало, кто зашел
    app_url = f"{WEB_URL}/app?user_id={user_id}&name={message.from_user.first_name}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть игру", web_app=WebAppInfo(url=app_url))]
    ])
    await message.answer("Добро пожаловать! Нажми кнопку, чтобы начать.", reply_markup=kb)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def update_energy(user):
    now = time.time()
    diff = now - user["last_energy_update"]
    regen = int(diff / 10) 
    if regen > 0:
        user["energy"] = min(100, user["energy"] + regen)
        user["last_energy_update"] = now

# --- API ---
async def handle_index(request):
    return web.FileResponse('index.html')

async def handle_state(request):
    user_id = request.query.get("user_id")
    user_name = request.query.get("name", "Игрок")
    
    if not user_id: 
        return web.json_response({"error": "No ID"}, status=400)

    # АВТО-РЕГИСТРАЦИЯ (чтобы при перезапуске сервера данные не пропадали из вида)
    if user_id not in users:
        users[user_id] = {
            "name": user_name,
            "gold": 1000,
            "energy": 100,
            "last_energy_update": time.time(),
            "owner_id": None
        }

    me = users[user_id]
    update_energy(me)

    # Формируем рынок (все, кроме меня)
    market = []
    for uid, u in users.items():
        if uid != user_id:
            market.append({
                "id": uid,
                "name": u["name"],
                "owner_id": u["owner_id"],
                "price": 1000 + (len(u["name"]) * 10)
            })

    # Формируем мою империю
    my_slaves = []
    for uid, u in users.items():
        if u["owner_id"] == user_id:
            my_slaves.append({"id": uid, "name": u["name"]})

    # Кто мой владелец
    my_owner = None
    if me["owner_id"] and me["owner_id"] in users:
        my_owner = users[me["owner_id"]]["name"]

    return web.json_response({
        "gold": me["gold"],
        "energy": me["energy"],
        "market": market,
        "my_slaves": my_slaves,
        "my_owner": my_owner
    })

async def handle_work(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    me = users.get(user_id)
    if me:
        update_energy(me)
        if me["energy"] >= 10:
            me["energy"] -= 10
            me["gold"] += 50
            return web.json_response({"success": True})
        return web.json_response({"success": False, "error": "Мало энергии!"})
    return web.json_response({"success": False, "error": "Нет игрока"})

async def handle_buy(request):
    data = await request.json()
    buyer_id = str(data.get("user_id"))
    target_id = str(data.get("target_id"))
    
    buyer = users.get(buyer_id)
    target = users.get(target_id)

    if not buyer or not target: 
        return web.json_response({"success": False, "error": "Ошибка данных"})
    
    price = 1000 + (len(target["name"]) * 10)

    if buyer["gold"] < price: 
        return web.json_response({"success": False, "error": "Не хватает золота!"})
    if target["owner_id"]: 
        return web.json_response({"success": False, "error": "Уже куплен!"})
    if target_id == buyer_id: 
        return web.json_response({"success": False, "error": "Нельзя себя!"})

    buyer["gold"] -= price
    target["owner_id"] = buyer_id
    return web.json_response({"success": True})

async def handle_redeem(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    me = users.get(user_id)
    if not me: 
        return web.json_response({"success": False, "error": "Ошибка"})
    if not me["owner_id"]: 
        return web.json_response({"success": False, "error": "Вы свободны!"})

    price = 1000 + (len(me["name"]) * 10)
    if me["gold"] < price: 
        return web.json_response({"success": False, "error": f"Нужно {price}💰"})
        
    me["gold"] -= price
    me["owner_id"] = None
    return web.json_response({"success": True})

async def main():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/app', handle_index)
    app.router.add_get('/api/state', handle_state)
    app.router.add_post('/api/work', handle_work)
    app.router.add_post('/api/buy', handle_buy)
    app.router.add_post('/api/redeem', handle_redeem)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    print(f"✅ Сервер запущен на порту {PORT}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
