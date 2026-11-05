import asyncio
import time
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9035696213:AAELU7MTMAtHquOr18HR0zsrvBzu_2FxOnE"
WEB_URL = "https://ripe-mails-marry.loca.lt" # БЕЗ слэша на конце!
PORT = 8080

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

users = {}
chat_members = {}

# --- ЛОГИКА БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    chat_id = message.chat.id
    # Ссылка на приложение с ID чата
    app_url = f"{WEB_URL}/app?chat_id={chat_id}"
    
    # ИСПОЛЬЗУЕМ url ВМЕСТО web_app (работает в группах)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть игру", url=app_url)]
    ])
    
    await message.answer(
        "Добро пожаловать в игру! Нажми кнопку ниже, чтобы начать выкупать участников этого чата.", 
        reply_markup=kb
    )

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_user(user_id, name="Игрок"):
    user_id = str(user_id)
    if user_id not in users:
        users[user_id] = {
            "name": name,
            "gold": 1000,
            "energy": 100,
            "last_energy_update": time.time(),
            "owner_id": None
        }
    return users[user_id]

def update_energy(user):
    now = time.time()
    diff = now - user["last_energy_update"]
    regen = int(diff / 10) 
    if regen > 0:
        user["energy"] = min(100, user["energy"] + regen)
        user["last_energy_update"] = now

# --- ЛОГИКА ВЕБ-СЕРВЕРА (API) ---
async def handle_index(request):
    return web.FileResponse('index.html')

async def handle_state(request):
    user_id = request.query.get("user_id")
    chat_id = request.query.get("chat_id")
    user_name = request.query.get("name", "Игрок")

    if not user_id or not chat_id:
        return web.json_response({"error": "Нет данных"}, status=400)

    user = get_user(user_id, user_name)
    update_energy(user)

    if chat_id not in chat_members:
        chat_members[chat_id] = []
    if str(user_id) not in chat_members[chat_id]:
        chat_members[chat_id].append(str(user_id))

    members_list = []
    for uid in chat_members[chat_id]:
        u = users.get(uid)
        if u:
            members_list.append({
                "id": uid,
                "name": u["name"],
                "owner_id": u["owner_id"],
                "is_me": (uid == str(user_id))
            })

    return web.json_response({
        "my_gold": user["gold"],
        "my_energy": user["energy"],
        "members": members_list
    })

async def handle_work(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    user = get_user(user_id)
    update_energy(user)

    if user["energy"] >= 10:
        user["energy"] -= 10
        user["gold"] += 50
        return web.json_response({"success": True, "gold": user["gold"], "energy": user["energy"]})
    else:
        return web.json_response({"success": False, "error": "Мало энергии!"})

async def handle_buy(request):
    data = await request.json()
    buyer_id = str(data.get("user_id"))
    target_id = str(data.get("target_id"))
    
    buyer = get_user(buyer_id)
    target = get_user(target_id)

    price = 1000

    if buyer["gold"] < price:
        return web.json_response({"success": False, "error": "Не хватает золота!"})
    
    if target["owner_id"] is not None:
        return web.json_response({"success": False, "error": "Он уже чей-то раб!"})

    buyer["gold"] -= price
    target["owner_id"] = buyer_id

    return web.json_response({"success": True, "gold": buyer["gold"]})

async def handle_boost(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    user = get_user(user_id)

    if user["gold"] >= 500:
        user["gold"] -= 500
        user["energy"] += 50
        if user["energy"] > 100: user["energy"] = 100 
        return web.json_response({"success": True, "gold": user["gold"], "energy": user["energy"]})
    return web.json_response({"success": False, "error": "Нужно 500 золота!"})

# --- ЗАПУСК ---
async def main():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/app', handle_index)
    app.router.add_get('/api/state', handle_state)
    app.router.add_post('/api/work', handle_work)
    app.router.add_post('/api/buy', handle_buy)
    app.router.add_post('/api/boost', handle_boost)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    print(f"✅ Сервер запущен на порту {PORT}")
    print(f"✅ Ссылка: {WEB_URL}")
    print("❗ Убедись, что CloudPub направлен на порт 8080!")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())