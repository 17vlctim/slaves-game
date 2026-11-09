import asyncio
import time
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = str(os.environ.get("ADMIN_ID", ""))
WEB_URL = "https://slaves-game.onrender.com" 
PORT = int(os.environ.get("PORT", 8080))

if not BOT_TOKEN:
    raise ValueError("Токен BOT_TOKEN не найден!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

users = {}
npcs = {
    "npc_1": {"name": "🧑‍🌾 Крестьянин", "rarity": "Обычный", "price": 500, "base_income": 10, "level": 1, "owner_id": None, "is_npc": True},
    "npc_2": {"name": "⚔️ Рыцарь", "rarity": "Редкий", "price": 1500, "base_income": 40, "level": 1, "owner_id": None, "is_npc": True},
    "npc_3": {"name": "🧙‍♂️ Маг", "rarity": "Эпический", "price": 3000, "base_income": 100, "level": 1, "owner_id": None, "is_npc": True},
}

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = str(message.from_user.id)
    user_name = message.from_user.first_name
    referrer_id = command.args
    
    if referrer_id and referrer_id != user_id and referrer_id in users:
        users[referrer_id]["gold"] += 500
        users[referrer_id]["ref_count"] = users[referrer_id].get("ref_count", 0) + 1

    if user_id not in users:
        users[user_id] = {
            "name": user_name, "gold": 1000, "energy": 100, 
            "last_energy_update": time.time(), "owner_id": None, 
            "last_collected": time.time(), "last_daily": 0,
            "ref_count": 0, "bought_count": 0, "sold_count": 0
        }

    app_url = f"{WEB_URL}/app?user_id={user_id}&name={user_name}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть игру", web_app=WebAppInfo(url=app_url))]
    ])
    await message.answer("Добро пожаловать в Империю! Нажми кнопку, чтобы начать.", reply_markup=kb)

def update_energy(user):
    now = time.time()
    diff = now - user["last_energy_update"]
    regen = int(diff / 10) 
    if regen > 0:
        user["energy"] = min(100, user["energy"] + regen)
        user["last_energy_update"] = now

async def handle_index(request):
    return web.FileResponse('index.html')

async def handle_state(request):
    user_id = request.query.get("user_id")
    user_name = request.query.get("name", "Игрок")
    
    if not user_id: return web.json_response({"error": "No ID"}, status=400)

    if user_id not in users:
        users[user_id] = {
            "name": user_name, "gold": 1000, "energy": 100, 
            "last_energy_update": time.time(), "owner_id": None, 
            "last_collected": time.time(), "last_daily": 0,
            "ref_count": 0, "bought_count": 0, "sold_count": 0
        }

    me = users[user_id]
    update_energy(me)

    all_entities = {**users, **npcs}
    my_slaves = []
    income_per_hour = 0

    # Считаем доход для всех игроков (для рейтинга)
    all_users_rating = []
    for uid, u in users.items():
        u_inc = 0
        for s in all_entities.values():
            if s["owner_id"] == uid:
                u_inc += (s["base_income"] * s["level"]) if s.get("is_npc") else 50
        all_users_rating.append({"id": uid, "name": u["name"], "gold": u["gold"], "income": u_inc})
        
        # Если это мои рабы, добавляем в список
        if u["owner_id"] == user_id:
            my_slaves.append({"id": uid, "name": u["name"], "rarity": "Игрок", "level": 1, "income": 50, "is_npc": False})
            income_per_hour += 50

    for uid, n in npcs.items():
        if n["owner_id"] == user_id:
            inc = n["base_income"] * n["level"]
            my_slaves.append({"id": uid, "name": n["name"], "rarity": n["rarity"], "level": n["level"], "income": inc, "is_npc": True})
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

    my_owner = None
    if me["owner_id"] and me["owner_id"] in all_entities:
        my_owner = all_entities[me["owner_id"]]["name"]

    bot_info = await bot.get_me()

    return web.json_response({
        "gold": me["gold"], "energy": me["energy"],
        "income_per_hour": income_per_hour, "pending_income": pending_income,
        "market": market, "my_slaves": my_slaves, "my_owner": my_owner,
        "is_admin": (str(user_id) == str(ADMIN_ID)),
        "can_daily": can_daily, 
        "leaderboard": all_users_rating, # Отдаем всех, фронт отсортирует
        "my_name": me["name"], "ref_count": me.get("ref_count", 0),
        "bought_count": me.get("bought_count", 0), "sold_count": me.get("sold_count", 0),
        "bot_username": bot_info.username
    })

# ... (остальные handle_ функции остаются без изменений: handle_collect, handle_work, handle_daily, handle_buy, handle_upgrade, handle_admin_cheat) ...
# Скопируй их из предыдущего сообщения, они не менялись.

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
    
    buyer["bought_count"] = buyer.get("bought_count", 0) + 1
    if not target.get("is_npc"):
        target["sold_count"] = target.get("sold_count", 0) + 1

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

async def handle_admin_cheat(request):
    try:
        data = await request.json()
        user_id = str(data.get("user_id"))
        amount = int(data.get("amount", 10000))
        
        if user_id == ADMIN_ID:
            if user_id not in users: return web.json_response({"success": False, "error": "Нет профиля"})
            users[user_id]["gold"] += amount
            return web.json_response({"success": True})
        return web.json_response({"success": False, "error": "Доступ запрещен"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

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
