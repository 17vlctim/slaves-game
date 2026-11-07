import asyncio
import time
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID", "") # Берем ID из настроек Render
WEB_URL = "https://slaves-game.onrender.com" 
PORT = int(os.environ.get("PORT", 8080))

if not BOT_TOKEN:
    raise ValueError("Токен BOT_TOKEN не найден в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (В ПАМЯТИ) ---
users = {}

npcs = {
    "npc_1": {"name": "🧑‍🌾 Крестьянин", "gold": 0, "energy": 0, "last_energy_update": 0, "owner_id": None, "price": 500, "income": 20, "is_npc": True},
    "npc_2": {"name": "⚔️ Рыцарь", "gold": 0, "energy": 0, "last_energy_update": 0, "owner_id": None, "price": 1500, "income": 60, "is_npc": True},
    "npc_3": {"name": "🧙‍♂️ Маг", "gold": 0, "energy": 0, "last_energy_update": 0, "owner_id": None, "price": 3000, "income": 120, "is_npc": True},
}

# --- ЛОГИКА БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    app_url = f"{WEB_URL}/app?user_id={user_id}&name={message.from_user.first_name}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть игру", web_app=WebAppInfo(url=app_url))]
    ])
    await message.answer("Добро пожаловать! Нажми кнопку, чтобы начать.", reply_markup=kb)

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

    if user_id not in users:
        users[user_id] = {"name": user_name, "gold": 1000, "energy": 100, "last_energy_update": time.time(), "owner_id": None, "is_npc": False}

    me = users[user_id]
    update_energy(me)

    market = []
    for uid, u in users.items():
        if uid != user_id and not u.get("is_npc"):
            market.append({"id": uid, "name": u["name"], "owner_id": u["owner_id"], "price": 1000 + (len(u["name"]) * 10), "is_npc": False})
            
    for uid, n in npcs.items():
        market.append({"id": uid, "name": n["name"], "owner_id": n["owner_id"], "price": n["price"], "is_npc": True})

    my_slaves = []
    for uid, u in {**users, **npcs}.items():
        if u["owner_id"] == user_id:
            income = u.get("income", 50)
            my_slaves.append({"id": uid, "name": u["name"], "is_npc": u.get("is_npc", False), "income": income})

    my_owner = None
    owner_id = me["owner_id"]
    if owner_id:
        all_entities = {**users, **npcs}
        if owner_id in all_entities:
            my_owner = all_entities[owner_id]["name"]

    # Проверяем, админ ли это (сравниваем с переменной окружения)
    is_admin = (str(user_id) == str(ADMIN_ID))

    return web.json_response({
        "gold": me["gold"], "energy": me["energy"],
        "market": market, "my_slaves": my_slaves, "my_owner": my_owner,
        "is_admin": is_admin
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
    
    all_entities = {**users, **npcs}
    buyer = users.get(buyer_id)
    target = all_entities.get(target_id)

    if not buyer or not target: return web.json_response({"success": False, "error": "Ошибка данных"})
    
    price = target.get("price", 1000 + (len(target["name"]) * 10))

    if buyer["gold"] < price: return web.json_response({"success": False, "error": "Не хватает золота!"})
    if target["owner_id"]: return web.json_response({"success": False, "error": "Уже куплен!"})
    if target_id == buyer_id: return web.json_response({"success": False, "error": "Нельзя себя!"})
    
    if target_id == buyer["owner_id"]:
        return web.json_response({"success": False, "error": "Нельзя купить своего владельца!"})

    buyer["gold"] -= price
    target["owner_id"] = buyer_id
    return web.json_response({"success": True})

async def handle_redeem(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    me = users.get(user_id)
    
    if not me or me.get("is_npc"): return web.json_response({"success": False, "error": "NPC не могут выкупать себя!"})
    if not me["owner_id"]: return web.json_response({"success": False, "error": "Вы свободны!"})

    price = 1000 + (len(me["name"]) * 10)
    if me["gold"] < price: return web.json_response({"success": False, "error": f"Нужно {price}💰"})
        
    me["gold"] -= price
    me["owner_id"] = None
    return web.json_response({"success": True})

async def handle_admin_cheat(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    amount = int(data.get("amount", 5000))
    
    if str(user_id) == str(ADMIN_ID) and user_id in users:
        users[user_id]["gold"] += amount
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Доступ запрещен"})

async def main():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/app', handle_index)
    app.router.add_get('/api/state', handle_state)
    app.router.add_post('/api/work', handle_work)
    app.router.add_post('/api/buy', handle_buy)
    app.router.add_post('/api/redeem', handle_redeem)
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
