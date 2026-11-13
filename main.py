import asyncio
import time
import os
import random
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

# Время старта сервера (для отсчета 7 дней ивента)
SERVER_START_TIME = time.time()
EVENT_DURATION = 7 * 24 * 60 * 60 # 7 дней в секундах

# --- БАЗА ДАННЫХ ---
users = {}
npcs = {
    "npc_1": {"name": "🧑‍🌾 Крестьянин", "rarity": "Обычный", "price": 500, "base_income": 10, "level": 1, "owner_id": None, "is_npc": True},
    "npc_2": {"name": "⚔️ Рыцарь", "rarity": "Редкий", "price": 1500, "base_income": 40, "level": 1, "owner_id": None, "is_npc": True},
    "npc_3": {"name": "🧙‍♂️ Маг", "rarity": "Эпический", "price": 3000, "base_income": 100, "level": 1, "owner_id": None, "is_npc": True},
    "npc_dragon": {"name": "🐉 Дракон", "rarity": "Легендарный", "price": 0, "base_income": 500, "level": 1, "owner_id": None, "is_npc": True}
}

CASE_LOOT = [
    {"type": "gold", "value": 5000, "weight": 40, "msg": "Выпало 5 000 золота!"},
    {"type": "gold", "value": 10000, "weight": 20, "msg": "Выпало 10 000 золота!"},
    {"type": "income_10h", "weight": 15, "msg": "Выпал доход за 10 часов!"},
    {"type": "frame", "value": "frame_fire", "weight": 10, "msg": "Выпала Рамка 'Огонь'!"},
    {"type": "frame", "value": "frame_neon", "weight": 8, "msg": "Выпала Рамка 'Неон'!"},
    {"type": "item", "value": "shield", "weight": 4, "msg": "Выпал Имперский Щит!"},
    {"type": "item", "value": "chains", "weight": 2, "msg": "Выпали Цепи!"},
    {"type": "npc", "value": "npc_dragon", "weight": 1, "msg": "НЕВЕРОЯТНО! Вы выбили Легендарного Дракона!"}
]

def create_user(user_id, name, referrer_id=None):
    if user_id not in users:
        while True:
            fake_id = random.randint(100000000, 999999999)
            if not any(u.get("game_id") == fake_id for u in users.values()):
                break
        
        start_gold = 1000
        start_crystals = 50 
        
        # Проверяем, идет ли еще ивент
        now = time.time()
        is_event_active = (now - SERVER_START_TIME) < EVENT_DURATION

        if referrer_id and referrer_id in users:
            if is_event_active:
                start_gold += 1000
                start_crystals += 20
                users[referrer_id]["gold"] += 1000
                users[referrer_id]["crystals"] += 20
            else:
                start_gold += 500 
                users[referrer_id]["gold"] += 500
            users[referrer_id]["ref_count"] = users[referrer_id].get("ref_count", 0) + 1

        users[user_id] = {
            "name": name, "gold": start_gold, "crystals": start_crystals, "energy": 100, 
            "last_energy_update": time.time(), "owner_id": None, 
            "last_collected": time.time(), "last_daily": 0,
            "last_ad_watch": 0, "ref_count": 0, "bought_count": 0, "sold_count": 0,
            "game_id": fake_id, "shield_until": 0, "chains_until": 0,
            "frame": "frame_basic", "name_color": "#ffffff",
            "inventory": [], "is_star": False, "is_oligarch": False, "last_boost": 0
        }
    return users[user_id]

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = str(message.from_user.id)
    user_name = message.from_user.first_name
    referrer_id = command.args
    
    create_user(user_id, user_name, referrer_id)

    app_url = f"{WEB_URL}/app?user_id={user_id}&name={user_name}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть Империю", web_app=WebAppInfo(url=app_url))]
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

    me = create_user(user_id, user_name)
    update_energy(me)

    now = time.time()
    all_entities = {**users, **npcs}
    my_slaves = []
    income_per_hour = 0
    all_users_rating = []
    
    # Проверка на Олигарха (первый, кто набрал 1 лям)
    if me["gold"] >= 1000000 and not me["is_oligarch"]:
        me["is_oligarch"] = True
        me["crystals"] += 500
        try:
            await bot.send_message(int(user_id), "👑 Поздравляем! Вы первый, кто накопил 1 000 000 монет! Вам присвоен титул Олигарх и начислено 500 💎!")
        except: pass

    # Множитель дохода, если Звезда
    star_multiplier = 1.5 if me.get("is_star") else 1.0

    for uid, u in users.items():
        u_inc = 0
        for s in all_entities.values():
            if s["owner_id"] == uid:
                u_inc += (s["base_income"] * s["level"]) if s.get("is_npc") else 50
        all_users_rating.append({"id": uid, "name": u["name"], "gold": u["gold"], "income": u_inc, "game_id": u["game_id"], "is_oligarch": u.get("is_oligarch", False), "is_star": u.get("is_star", False)})
        
        if u["owner_id"] == user_id:
            my_slaves.append({"id": uid, "name": u["name"], "rarity": "Игрок", "level": 1, "income": 50, "is_npc": False, "game_id": u["game_id"]})
            income_per_hour += 50

    for uid, n in npcs.items():
        if n["owner_id"] == user_id:
            inc = n["base_income"] * n["level"]
            my_slaves.append({"id": uid, "name": n["name"], "rarity": n["rarity"], "level": n["level"], "income": inc, "is_npc": True, "game_id": None})
            income_per_hour += inc

    income_per_hour = int(income_per_hour * star_multiplier)

    # Ограничение офлайна 8 часов
    hours_passed = min(8, (now - me["last_collected"]) / 3600)
    pending_income = int(hours_passed * income_per_hour)
    can_daily = (now - me["last_daily"]) > 86400
    can_watch_ad = (now - me["last_ad_watch"]) > 3600
    can_boost = (now - me.get("last_boost", 0)) > (4 * 3600)

    market = []
    for uid, u in users.items():
        if uid != user_id:
            market.append({"id": uid, "name": u["name"], "owner_id": u["owner_id"], "price": 1000 + (len(u["name"]) * 10), "rarity": "Игрок", "is_npc": False, "game_id": u["game_id"], "shield": u.get("shield_until", 0) > now, "frame": u.get("frame", "frame_basic"), "name_color": u.get("name_color", "#ffffff"), "is_star": u.get("is_star", False)})
    for uid, n in npcs.items():
        market.append({"id": uid, "name": n["name"], "owner_id": n["owner_id"], "price": n["price"], "rarity": n["rarity"], "is_npc": True, "game_id": None, "shield": False, "frame": "frame_basic", "name_color": "#ffffff", "is_star": False})

    my_owner = None
    if me["owner_id"] and me["owner_id"] in all_entities:
        my_owner = all_entities[me["owner_id"]]["name"]

    bot_info = await bot.get_me()

    # Считаем оставшееся время ивента
    time_left = max(0, int(EVENT_DURATION - (now - SERVER_START_TIME)))

    return web.json_response({
        "gold": me["gold"], "crystals": me["crystals"], "energy": me["energy"],
        "income_per_hour": income_per_hour, "pending_income": pending_income,
        "market": market, "my_slaves": my_slaves, "my_owner": my_owner,
        "is_admin": (str(user_id) == str(ADMIN_ID)),
        "can_daily": can_daily, "can_watch_ad": can_watch_ad, "can_boost": can_boost,
        "has_shield": me.get("shield_until", 0) > now,
        "leaderboard": all_users_rating,
        "my_name": me["name"], "my_game_id": me["game_id"],
        "ref_count": me.get("ref_count", 0), "bought_count": me.get("bought_count", 0), "sold_count": me.get("sold_count", 0),
        "bot_username": bot_info.username,
        "my_frame": me.get("frame", "frame_basic"), "my_name_color": me.get("name_color", "#ffffff"), "my_inventory": me.get("inventory", []),
        "is_star": me.get("is_star", False), "is_oligarch": me.get("is_oligarch", False),
        "event_time_left": time_left
    })

async def handle_boost(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    me = users.get(user_id)
    now = time.time()
    
    if me and (now - me.get("last_boost", 0)) > (4 * 3600):
        me["last_boost"] = now
        me["last_collected"] = now - (1 * 3600) # Даем бонус как будто час прошел
        return web.json_response({"success": True, "msg": "Бустер активирован! Вы получили доход за 1 час вперед."})
    return web.json_response({"success": False, "error": "Бустер еще не готов!"})

# ... (все остальные функции: case_info, user_info, collect, work, daily, watch_ad, buy, hire_assassin, redeem, upgrade, admin_cheat, buy_item, open_case, equip_frame, change_color, buy_frame остаются как были) ...
# ВСТАВЬ ИХ СЮДА ИЗ ПРЕДЫДУЩЕГО СООБЩЕНИЯ, ОНИ РАБОТАЮТ.

async def handle_case_info(request):
    total_weight = sum(item["weight"] for item in CASE_LOOT)
    loot_info = []
    for item in CASE_LOOT:
        chance = round((item["weight"] / total_weight) * 100, 1)
        name, icon = "", ""
        if item["type"] == "gold": name, icon = f"{item['value']} Золота", "💰"
        elif item["type"] == "income_10h": name, icon = "Доход за 10 часов", "⏳"
        elif item["type"] == "frame": 
            name, icon = "Рамка профиля", "🖼️"
            if item["value"] == "frame_fire": name = "Рамка 'Огонь'"
            if item["value"] == "frame_neon": name = "Рамка 'Неон'"
        elif item["type"] == "item":
            if item["value"] == "shield": name, icon = "Имперский Щит (3ч)", "🛡️"
            if item["value"] == "chains": name, icon = "Цепи (12ч)", "⛓️"
        elif item["type"] == "npc": name, icon = "Легендарный NPC: Дракон", "🐉"
        loot_info.append({"name": name, "icon": icon, "chance": chance})
    loot_info.sort(key=lambda x: x["chance"])
    return web.json_response({"loot": loot_info})

async def handle_user_info(request):
    target_id = request.query.get("target_id")
    if not target_id: return web.json_response({"error": "No ID"}, status=400)
    target_user = users.get(target_id)
    if not target_user: return web.json_response({"error": "Игрок не найден"}, status=404)
    all_entities = {**users, **npcs}
    target_income, target_slaves = 0, []
    for uid, u in all_entities.items():
        if u["owner_id"] == target_id:
            if u.get("is_npc"):
                inc = u["base_income"] * u["level"]
                target_slaves.append({"id": uid, "name": u["name"], "rarity": u["rarity"], "income": inc, "is_npc": True})
            else:
                inc = 50
                target_slaves.append({"id": uid, "name": u["name"], "rarity": "Игрок", "income": inc, "is_npc": False, "game_id": u["game_id"]})
            target_income += inc
    target_owner_name = None
    if target_user["owner_id"] and target_user["owner_id"] in all_entities:
        target_owner_name = all_entities[target_user["owner_id"]]["name"]
    return web.json_response({"name": target_user["name"], "gold": target_user["gold"], "income": target_income, "slaves": target_slaves, "owner_name": target_owner_name, "id": target_id, "game_id": target_user["game_id"], "frame": target_user.get("frame", "frame_basic"), "name_color": target_user.get("name_color", "#ffffff"), "is_star": target_user.get("is_star", False)})

async def handle_collect(request):
    data = await request.json(); user_id = str(data.get("user_id")); me = users.get(user_id)
    if not me: return web.json_response({"success": False})
    income_per_hour = 0
    for u in {**users, **npcs}.values():
        if u["owner_id"] == user_id: income_per_hour += (u["base_income"] * u["level"]) if u.get("is_npc") else 50
    if me.get("is_star"): income_per_hour = int(income_per_hour * 1.5)
    
    now = time.time(); hours_passed = min(8, (now - me["last_collected"]) / 3600); pending = int(hours_passed * income_per_hour)
    if pending <= 0: return web.json_response({"success": False, "error": "Нечего забирать"})
    me["gold"] += pending; me["last_collected"] = now
    return web.json_response({"success": True})

async def handle_work(request):
    data = await request.json(); user_id = str(data.get("user_id")); me = users.get(user_id)
    if me:
        update_energy(me)
        if me["energy"] >= 10:
            me["energy"] -= 10; me["gold"] += 50
            return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Мало энергии!"})

async def handle_daily(request):
    data = await request.json(); user_id = str(data.get("user_id")); me = users.get(user_id); now = time.time()
    if me and (now - me["last_daily"]) > 86400:
        me["gold"] += 500; me["last_daily"] = now
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Бонус еще не готов!"})

async def handle_watch_ad(request):
    data = await request.json(); user_id = str(data.get("user_id")); me = users.get(user_id); now = time.time()
    if me and (now - me.get("last_ad_watch", 0)) > 3600:
        me["gold"] += 250; me["last_ad_watch"] = now
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Кулдаун!"})

async def handle_buy(request):
    data = await request.json(); buyer_id = str(data.get("user_id")); target_id = str(data.get("target_id"))
    all_entities = {**users, **npcs}; buyer = users.get(buyer_id); target = all_entities.get(target_id)
    if not buyer or not target: return web.json_response({"success": False, "error": "Ошибка"})
    now = time.time()
    if target.get("shield_until", 0) > now: return web.json_response({"success": False, "error": "У игрока активен Имперский Щит!"})
    price = target.get("price", 1000 + (len(target["name"]) * 10))
    if buyer["gold"] < price: return web.json_response({"success": False, "error": "Нет денег!"})
    if target["owner_id"]: return web.json_response({"success": False, "error": "Уже куплен!"})
    if target_id == buyer_id: return web.json_response({"success": False, "error": "Нельзя себя!"})
    if target_id == buyer["owner_id"]: return web.json_response({"success": False, "error": "Нельзя владельца!"})
    
    buyer["gold"] -= price; target["owner_id"] = buyer_id
    buyer["bought_count"] = buyer.get("bought_count", 0) + 1
    if not target.get("is_npc"): target["sold_count"] = target.get("sold_count", 0) + 1
    
    if not target.get("is_npc"):
        try: await bot.send_message(int(target_id), f"😡 <b>{buyer['name']}</b> купил тебя за <b>{price} монет</b>!\nТы теперь его раб. Зайди в игру и выкупи себя или найми убийцу!")
        except: pass
    return web.json_response({"success": True})

async def handle_hire_assassin(request):
    data = await request.json(); user_id = str(data.get("user_id")); me = users.get(user_id)
    if not me or not me.get("owner_id"): return web.json_response({"success": False, "error": "Ты не раб!"})
    if me["crystals"] < 100: return web.json_response({"success": False, "error": "Нужно 100 💎!"})
    
    me["crystals"] -= 100
    owner_id = me["owner_id"]; owner_name = users[owner_id]["name"] if owner_id in users else "Неизвестный"
    me["owner_id"] = None
    try: await bot.send_message(int(owner_id), f"🔪 <b>{me['name']}</b> нанял убийцу и сбежал от тебя!")
    except: pass
    return web.json_response({"success": True, "msg": f"Ты заплатил убийце и сбежал от {owner_name}!"})

async def handle_redeem(request):
    data = await request.json(); user_id = str(data.get("user_id")); me = users.get(user_id)
    if not me or me.get("is_npc"): return web.json_response({"success": False, "error": "Ошибка"})
    if not me["owner_id"]: return web.json_response({"success": False, "error": "Вы свободны!"})
    price = 1000 + (len(me["name"]) * 10)
    if me["gold"] < price: return web.json_response({"success": False, "error": f"Нужно {price}💰"})
    me["gold"] -= price; me["owner_id"] = None
    return web.json_response({"success": True})

async def handle_upgrade(request):
    data = await request.json(); user_id = str(data.get("user_id")); target_id = str(data.get("target_id"))
    target = npcs.get(target_id); me = users.get(user_id)
    if not target or target["owner_id"] != user_id: return web.json_response({"success": False, "error": "Это не твой NPC"})
    cost = target["base_income"] * 100 * target["level"]
    if me["gold"] < cost: return web.json_response({"success": False, "error": f"Нужно {cost}💰"})
    me["gold"] -= cost; target["level"] += 1
    return web.json_response({"success": True})

async def handle_admin_cheat(request):
    try:
        data = await request.json(); user_id = str(data.get("user_id")); amount = int(data.get("amount", 10000)); item_type = data.get("type", "gold")
        if user_id == ADMIN_ID:
            if item_type == "gold": users[user_id]["gold"] += amount
            elif item_type == "crystals": users[user_id]["crystals"] += amount
            elif item_type == "star": users[user_id]["is_star"] = True
            return web.json_response({"success": True})
        return web.json_response({"success": False, "error": "Доступ запрещен"})
    except Exception as e: return web.json_response({"success": False, "error": str(e)})

async def handle_buy_item(request):
    data = await request.json(); user_id = str(data.get("user_id")); item_type = data.get("item"); me = users.get(user_id)
    if not me: return web.json_response({"success": False})
    now = time.time()
    if item_type == "shield":
        if me["crystals"] < 15: return web.json_response({"success": False, "error": "Не хватает кристаллов!"})
        me["crystals"] -= 15; me["shield_until"] = now + (3 * 3600)
        return web.json_response({"success": True, "msg": "Щит активирован на 3 часа!"})
    elif item_type == "chains":
        if me["crystals"] < 20: return web.json_response({"success": False, "error": "Не хватает кристаллов!"})
        me["crystals"] -= 20; me["chains_until"] = now + (12 * 3600)
        return web.json_response({"success": True, "msg": "Цепи накинуты на рабов!"})
    return web.json_response({"success": False})

async def handle_open_case(request):
    data = await request.json(); user_id = str(data.get("user_id")); me = users.get(user_id)
    if not me: return web.json_response({"success": False})
    if me["crystals"] < 25: return web.json_response({"success": False, "error": "Нужно 25 кристаллов!"})
    me["crystals"] -= 25
    total_weight = sum(item["weight"] for item in CASE_LOOT)
    rand_val = random.uniform(0, total_weight)
    current_weight = 0
    selected_loot = CASE_LOOT[0]
    for item in CASE_LOOT:
        current_weight += item["weight"]
        if rand_val <= current_weight: selected_loot = item; break
    loot_msg = selected_loot["msg"]; loot_type = selected_loot["type"]
    if loot_type == "gold": me["gold"] += selected_loot["value"]
    elif loot_type == "income_10h":
        income_per_hour = 0
        for u in {**users, **npcs}.values():
            if u["owner_id"] == user_id: income_per_hour += (u["base_income"] * u["level"]) if u.get("is_npc") else 50
        if income_per_hour == 0: income_per_hour = 50
        me["gold"] += income_per_hour * 10
    elif loot_type == "frame":
        if selected_loot["value"] not in me["inventory"]: me["inventory"].append(selected_loot["value"])
    elif loot_type == "item":
        if selected_loot["value"] == "shield": me["shield_until"] = time.time() + (3 * 3600)
        elif selected_loot["value"] == "chains": me["chains_until"] = time.time() + (12 * 3600)
    elif loot_type == "npc":
        if npcs["npc_dragon"]["owner_id"] is None: npcs["npc_dragon"]["owner_id"] = user_id
        else: me["gold"] += 15000; loot_msg = "Дракон уже занят. Компенсация: 15 000 золота!"
    return web.json_response({"success": True, "msg": loot_msg})

async def handle_equip_frame(request):
    data = await request.json(); user_id = str(data.get("user_id")); frame = data.get("frame"); me = users.get(user_id)
    if me and (frame in me["inventory"] or frame == "frame_basic"):
        me["frame"] = frame
        return web.json_response({"success": True, "msg": "Рамка надета!"})
    return web.json_response({"success": False, "error": "Рамка не найдена"})

async def handle_change_color(request):
    data = await request.json(); user_id = str(data.get("user_id")); color = data.get("color"); cost = 5
    me = users.get(user_id)
    if me["crystals"] < cost: return web.json_response({"success": False, "error": f"Нужно {cost} 💎"})
    me["crystals"] -= cost; me["name_color"] = color
    return web.json_response({"success": True, "msg": "Цвет изменен!"})

async def handle_buy_frame(request):
    data = await request.json(); user_id = str(data.get("user_id")); frame = data.get("frame"); currency = data.get("currency")
    me = users.get(user_id)
    frames_db = {"frame_gold": {"price": 50, "currency": "crystals"}, "frame_blood": {"price": 25000, "currency": "gold"}}
    if frame not in frames_db: return web.json_response({"success": False})
    item = frames_db[frame]
    if item["currency"] == "crystals" and me["crystals"] >= item["price"]:
        me["crystals"] -= item["price"]
        if frame not in me["inventory"]: me["inventory"].append(frame)
        return web.json_response({"success": True, "msg": "Рамка куплена!"})
    elif item["currency"] == "gold" and me["gold"] >= item["price"]:
        me["gold"] -= item["price"]
        if frame not in me["inventory"]: me["inventory"].append(frame)
        return web.json_response({"success": True, "msg": "Рамка куплена!"})
    return web.json_response({"success": False, "error": "Не хватает средств!"})

async def main():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/app', handle_index)
    app.router.add_get('/api/state', handle_state)
    app.router.add_get('/api/case_info', handle_case_info)
    app.router.add_get('/api/user_info', handle_user_info)
    app.router.add_post('/api/work', handle_work)
    app.router.add_post('/api/collect', handle_collect)
    app.router.add_post('/api/daily', handle_daily)
    app.router.add_post('/api/watch_ad', handle_watch_ad)
    app.router.add_post('/api/boost', handle_boost)
    app.router.add_post('/api/buy', handle_buy)
    app.router.add_post('/api/redeem', handle_redeem)
    app.router.add_post('/api/upgrade', handle_upgrade)
    app.router.add_post('/api/admin_cheat', handle_admin_cheat)
    app.router.add_post('/api/buy_item', handle_buy_item)
    app.router.add_post('/api/open_case', handle_open_case)
    app.router.add_post('/api/equip_frame', handle_equip_frame)
    app.router.add_post('/api/change_color', handle_change_color)
    app.router.add_post('/api/buy_frame', handle_buy_frame)
    app.router.add_post('/api/hire_assassin', handle_hire_assassin)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"✅ Сервер запущен на порту {PORT}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
