import asyncio
import time
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = str(os.environ.get("ADMIN_ID", "")) # Приводим к строке
WEB_URL = "https://slaves-game.onrender.com" 
PORT = int(os.environ.get("PORT", 8080))

if not BOT_TOKEN:
    raise ValueError("Токен BOT_TOKEN не найден в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (В ПАМЯТИ) ---
users = {}

npcs = {
    "npc_1": {"name": "🧑‍🌾 Крестьянин", "rarity": "Обычный", "price": 500, "base_income": 10, "level": 1, "owner_id": None, "is_npc": True},
    "npc_2": {"name": "⚔️ Рыцарь", "rarity": "Редкий", "price": 1500, "base_income": 40, "level": 1, "owner_id": None, "is_npc": True},
    "npc_3": {"name": "🧙‍♂️ Маг", "rarity": "Эпический", "price": 3000, "base_income": 100, "level": 1, "owner_id": None, "is_npc": True},
}

# --- ЛОГИКА БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    app_url = f"{WEB_URL}/app?user_id={user_id}&name={message.from_user.first_name}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть игру", web_app=WebAppInfo(url=app_url))]
    ])
    await message.answer("Добро пожаловать в Империю! Нажми кнопку, чтобы начать.", reply_markup=kb)

def create_user(user_id, name):
    if user_id not in users:
        users[user_id] = {
            "name": name, "gold": 1000, "energy": 100, 
            "last_energy_update": time.time(), "owner_id": None, 
            "last_collected": time.time(), "last_daily": 0
        }
    return users[user_id]

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
    
    if not user_id: return web.json_response({"error": "No ID"}, status=400)

    me = create_user(user_id, user_name)
    update_energy(me)

    income_per_hour = 0
    all_entities = {**users, **npcs}
    
    my_slaves = []
    for uid, u in all_entities.items():
        if u["owner_id"] == user_id:
            if u.get("is_npc"):
                inc = u["base_income"] * u["level"]
                my_slaves.append({"id": uid, "name": u["name"], "rarity": u["rarity"], "level": u["level"], "income": inc, "is_npc": True})
            else:
                inc = 50
                my_slaves.append({"id": uid, "name": u["name"], "rarity": "Игрок", "level": 1, "income": inc, "is_npc": False})
            income_per_hour += inc

    now = time.time()
    hours_passed = min(24, (now - me["last_collected"]) / 3600)
    pending_income = int(hours_passed * income_per_hour)
    can_daily = (now - me["last_daily"]) > 86400

    market = []
    for uid, u in users.items():
        if uid != user_id:
            market.append({"id": uid, "name": u["name"], "owner_id": u["owner_id"], "price": 1000 + (len(u["name"]) * 10), "rarity": "Игрок", "is_npc": False})
    for uid, n in npcs.items():
        market.append({"id": uid, "name": n["name"], "owner_id": n["owner_id"], "price": n["price"], "rarity": n["rarity"], "is_npc": True})

    sorted_users = sorted(users.values(), key=lambda x: x["gold"], reverse=True)
    leaderboard = [{"name": u["name"], "gold": u["gold"]} for u in sorted_users[:5]]

    my_owner = None
    if me["owner_id"] and me["owner_id"] in all_entities:
        my_owner = all_entities[me["owner_id"]]["name"]

    return web.json_response({
        "gold": me["gold"], "energy": me["energy"],
        "income_per_hour": income_per_hour, "pending_income": pending_income,
        "market": market, "my_slaves": my_slaves, "my_owner": my_owner,
        "is_admin": (str(user_id) == str(ADMIN_ID)),
        "can_daily": can_daily, "leaderboard": leaderboard
    })

async def handle_collect(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    me = users.get(user_id)
    if not me: return web.json_response({"success": False})
    
    income_per_hour = 0
    for u in {**users, **npcs}.values():
        if u["owner_id"] == user_id:
            income_per_hour += (u["base_income"] * u["level"]) if u.get("is_npc") else 50
        
    now = time.time()
    hours_passed = min(24, (now - me["last_collected"]) / 3600)
    pending = int(hours_passed * income_per_hour)

    if pending <= 0: return web.json_response({"success": False, "error": "Нечего забирать"})
    me["gold"] += pending
    me["last_collected"] = now
    return web.json_response({"success": True})

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

async def handle_daily(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    me = users.get(user_id)
    now = time.time()
    
    if me and (now - me["last_daily"]) > 86400:
        me["gold"] += 500
        me["last_daily"] = now
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Бонус еще не готов!"})

async def handle_buy(request):
    data = await request.json()
    buyer_id = str(data.get("user_id"))
    target_id = str(data.get("target_id"))
    
    all_entities = {**users, **npcs}
    buyer = users.get(buyer_id)
    target = all_entities.get(target_id)

    if not buyer or not target: return web.json_response({"success": False, "error": "Ошибка"})
    
    price = target.get("price", 1000 + (len(target["name"]) * 10))

    if buyer["gold"] < price: return web.json_response({"success": False, "error": "Нет денег!"})
    if target["owner_id"]: return web.json_response({"success": False, "error": "Уже куплен!"})
    if target_id == buyer_id: return web.json_response({"success": False, "error": "Нельзя себя!"})
    if target_id == buyer["owner_id"]: return web.json_response({"success": False, "error": "Нельзя владельца!"})

    buyer["gold"] -= price
    target["owner_id"] = buyer_id
    return web.json_response({"success": True})

async def handle_upgrade(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    target_id = str(data.get("target_id"))
    
    target = npcs.get(target_id)
    me = users.get(user_id)
    
    if not target or target["owner_id"] != user_id: return web.json_response({"success": False, "error": "Это не твой NPC"})
    
    cost = target["base_income"] * 100 * target["level"]
    if me["gold"] < cost: return web.json_response({"success": False, "error": f"Нужно {cost}💰"})

    me["gold"] -= cost
    target["level"] += 1
    return web.json_response({"success": True})

# ИСПРАВЛЕННАЯ АДМИНКА
async def handle_admin_cheat(request):
    try:
        data = await request.json()
        user_id = str(data.get("user_id"))
        amount = int(data.get("amount", 10000))
        
        if user_id == ADMIN_ID:
            # Если игрока нет в памяти (после перезапуска), создаем его
            if user_id not in users:
                create_user(user_id, "Владелец")
            
            users[user_id]["gold"] += amount
            return web.json_response({"success": True})
        return web.json_response({"success": False, "error": "Доступ запрещен"})
    except Exception as e:
        print("Ошибка в админке:", e)
        return web.json_response({"success": False, "error": "Ошибка сервера"})

async def main():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/app', handle_index)
    app.router.add_get('/api/state', handle_state)
    app.router.add_post('/api/work', handle_work)
    app.router.add_post('/api/collect', handle_collect)
    app.router.add_post('/api/daily', handle_daily)
    app.router.add_post('/api/buy', handle_buy)
    app.router.add_post('/api/upgrade', handle_upgrade)
    app.router.add_post('/api/admin_cheat', handle_admin_cheat)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    print(f"✅ Сервер запущен на порту {PORT}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
