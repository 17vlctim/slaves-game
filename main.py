import asyncio
import time
import os
import random
import hmac
import hashlib
from urllib.parse import parse_qsl
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

SERVER_START_TIME = time.time()
EVENT_DURATION = 7 * 24 * 60 * 60 # 7 дней
EVENT_ENDED = False

users = {}
npcs = {
    "npc_dragon": {"name": "🐉 Дракон", "rarity": "Легендарный", "base_income": 500, "owner_id": None}
}

CASE_LOOT = [
    {"type": "gold", "value": 5000, "weight": 35, "msg": "Выпало 5 000 золота!", "icon": "💰"},
    {"type": "gold", "value": 10000, "weight": 15, "msg": "Выпало 10 000 золота!", "icon": "💰"},
    {"type": "income_10h", "weight": 15, "msg": "Выпал доход за 10 часов!", "icon": "⏳"},
    {"type": "frame", "value": "frame_fire", "weight": 10, "msg": "Выпала Рамка 'Огонь'!", "icon": "🖼️"},
    {"type": "frame", "value": "frame_neon", "weight": 8, "msg": "Выпала Рамка 'Неон'!", "icon": "🖼️"},
    {"type": "avatar", "value": "avatar_2", "weight": 8, "msg": "Выпала Аватарка 'Рыцарь'!", "icon": "👤"},
    {"type": "avatar", "value": "avatar_3", "weight": 5, "msg": "Выпала Аватарка 'Маг'!", "icon": "👤"},
    {"type": "item", "value": "shield", "weight": 2, "msg": "Выпал Имперский Щит!", "icon": "🛡️"},
    {"type": "item", "value": "chains", "weight": 1, "msg": "Выпали Цепи!", "icon": "⛓️"},
    {"type": "npc", "value": "npc_dragon", "weight": 1, "msg": "НЕВЕРОЯТНО! Вы выбили Легендарного Дракона!", "icon": "🐉"}
]

# --- БЕЗОПАСНОСТЬ (ПРОВЕРКА INITDATA) ---
def check_webapp_signature(init_data: str) -> dict:
    if not init_data: return None
    try:
        parsed_data = dict(parse_qsl(init_data))
        if "hash" not in parsed_data: return None
        hash_str = parsed_data.pop('hash')
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if calculated_hash == hash_str:
            return parsed_data
        return None
    except Exception:
        return None

def get_user_id_from_request(request):
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        # Для локального теста без заголовков (в проде лучше убрать)
        fallback = request.query.get("user_id")
        if fallback and os.environ.get("DEBUG_MODE") == "True":
            return fallback
        return None
    
    parsed = check_webapp_signature(init_data)
    if parsed and "user" in parsed:
        import json
        user_info = json.loads(parsed["user"])
        return str(user_info["id"])
    return None

def calculate_income_per_hour(user):
    income = 0
    # Доход от купленных игроков
    for uid, u in users.items():
        if u.get("owner_id") == user["tg_id"]:
            income += 50
    
    # Доход от NPC
    for npc_id, n in npcs.items():
        if n.get("owner_id") == user["tg_id"]:
            income += n["base_income"]

    # Множители
    star_multiplier = 1.5 if user.get("is_star") else 1.0
    event_multiplier = 1.5 if user.get("event_buff_until", 0) > time.time() else 1.0
    
    return int(income * star_multiplier * event_multiplier)

def update_income_before_change(user):
    now = time.time()
    hours_passed = min(8, (now - user["last_collected"]) / 3600)
    current_income = calculate_income_per_hour(user)
    user["pending_income"] = user.get("pending_income", 0) + int(hours_passed * current_income)
    user["last_collected"] = now

def create_user(user_id, name, referrer_id=None):
    if user_id not in users:
        while True:
            fake_id = random.randint(100000000, 999999999)
            if not any(u.get("game_id") == fake_id for u in users.values()):
                break
        
        start_gold = 1000
        start_crystals = 50 
        
        now = time.time()
        is_event_active = (now - SERVER_START_TIME) < EVENT_DURATION

        if referrer_id and referrer_id in users and referrer_id != user_id:
            if is_event_active:
                start_gold += 1000
                users[referrer_id]["gold"] += 1000
                users[referrer_id]["crystals"] += 20
                users[referrer_id]["event_buff_until"] = now + (24 * 3600)
                users[referrer_id]["event_ref_count"] = users[referrer_id].get("event_ref_count", 0) + 1
            else:
                start_gold += 500 
                users[referrer_id]["gold"] += 500
            
            users[referrer_id]["ref_count"] = users[referrer_id].get("ref_count", 0) + 1

        users[user_id] = {
            "tg_id": user_id, "name": name, "gold": start_gold, "crystals": start_crystals, 
            "last_collected": time.time(), "pending_income": 0,
            "owner_id": None, "last_daily": 0, "last_ad_watch": 0, 
            "ref_count": 0, "event_ref_count": 0, "bought_count": 0, "sold_count": 0,
            "game_id": fake_id, "shield_until": 0, "chains_until": 0,
            "frame": "frame_basic", "avatar": "avatar_1", "name_color": "#ffffff",
            "inventory": [], "is_star": False, "is_oligarch": False, "last_boost": 0,
            "event_buff_until": 0, "referrer_id": referrer_id
        }
    return users[user_id]

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = str(message.from_user.id)
    user_name = message.from_user.first_name
    referrer_id = command.args
    
    create_user(user_id, user_name, referrer_id)

    app_url = f"{WEB_URL}/app"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть Империю", web_app=WebAppInfo(url=app_url))]
    ])
    await message.answer("Добро пожаловать в Royal Empire! Нажми кнопку, чтобы начать.", reply_markup=kb)

async def handle_index(request):
    return web.FileResponse('index.html')

# --- API ---
async def handle_state(request):
    user_id = get_user_id_from_request(request)
    if not user_id:
        # Для теста в браузере
        user_id = request.query.get("user_id")
        if not user_id: return web.json_response({"error": "Unauthorized"}, status=401)
        user_name = request.query.get("name", "Игрок")
        create_user(user_id, user_name)
    else:
        user_name = users[user_id]["name"]

    me = users[user_id]
    
    # Автоматическая регистрация Олигарха
    if me["gold"] >= 1000000 and not me["is_oligarch"]:
        me["is_oligarch"] = True
        me["crystals"] += 500

    # Расчет накопленного дохода (для отображения)
    now = time.time()
    hours_passed = min(8, (now - me["last_collected"]) / 3600)
    current_income = calculate_income_per_hour(me)
    display_pending = me.get("pending_income", 0) + int(hours_passed * current_income)

    # Рынок (ТОЛЬКО ИГРОКИ, БЕЗ NPC)
    market = []
    for uid, u in users.items():
        if uid != user_id:
            market.append({
                "id": uid, "name": u["name"], "owner_id": u["owner_id"], 
                "price": 1000 + (len(u["name"]) * 10), 
                "rarity": "Игрок", "game_id": u["game_id"], 
                "shield": u.get("shield_until", 0) > now, 
                "frame": u.get("frame", "frame_basic"), 
                "name_color": u.get("name_color", "#ffffff"), 
                "is_star": u.get("is_star", False), 
                "income": 50, 
                "avatar": u.get("avatar", "avatar_1")
            })

    # Мои рабы
    my_slaves = []
    for uid, u in users.items():
        if u["owner_id"] == user_id:
            my_slaves.append({"id": uid, "name": u["name"], "rarity": "Игрок", "income": 50, "avatar": u.get("avatar", "avatar_1")})
            
    for npc_id, n in npcs.items():
        if n["owner_id"] == user_id:
            my_slaves.append({"id": npc_id, "name": n["name"], "rarity": n["rarity"], "income": n["base_income"], "avatar": "npc_dragon.jpg"})

    # Владелец
    my_owner = None
    if me["owner_id"] and me["owner_id"] in users:
        my_owner = users[me["owner_id"]]["name"]

    bot_info = await bot.get_me()
    time_left = max(0, int(EVENT_DURATION - (now - SERVER_START_TIME)))

    return web.json_response({
        "gold": me["gold"], "crystals": me["crystals"],
        "income_per_hour": current_income, 
        "pending_income": display_pending,
        "market": market, "my_slaves": my_slaves, "my_owner": my_owner,
        "is_admin": (str(user_id) == str(ADMIN_ID)),
        "can_daily": (now - me["last_daily"]) > 86400, 
        "can_watch_ad": (now - me["last_ad_watch"]) > 3600, 
        "can_boost": (now - me.get("last_boost", 0)) > (4 * 3600),
        "has_shield": me.get("shield_until", 0) > now,
        "has_chains": me.get("chains_until", 0) > now,
        "leaderboard": [{"id": uid, "name": u["name"], "gold": u["gold"], "income": 0, "game_id": u["game_id"], "is_oligarch": u.get("is_oligarch", False), "is_star": u.get("is_star", False)} for uid, u in users.items()],
        "my_name": me["name"], "my_game_id": me["game_id"],
        "ref_count": me.get("ref_count", 0), "event_ref_count": me.get("event_ref_count", 0),
        "bought_count": me.get("bought_count", 0), "sold_count": me.get("sold_count", 0),
        "bot_username": bot_info.username,
        "my_frame": me.get("frame", "frame_basic"), "my_avatar": me.get("avatar", "avatar_1"), "my_name_color": me.get("name_color", "#ffffff"), "my_inventory": me.get("inventory", []),
        "is_star": me.get("is_star", False), "is_oligarch": me.get("is_oligarch", False),
        "event_time_left": time_left
    })

async def handle_work(request):
    user_id = get_user_id_from_request(request) or request.query.get("user_id")
    if not user_id or user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    
    # Восстановление энергии (упрощенно, просто даем монеты с лимитом в час)
    if time.time() - me.get("last_work", 0) > 3:
        me["last_work"] = time.time()
        me["gold"] += 50
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Кулдаун 3 сек!"})

async def handle_collect(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    if not user_id or user_id not in users: return web.json_response({"success": False})
    
    me = users[user_id]
    update_income_before_change(me)
    
    if me["pending_income"] > 0:
        me["gold"] += me["pending_income"]
        me["pending_income"] = 0
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Нечего собирать!"})

async def handle_boost(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    if not user_id or user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    now = time.time()
    
    if (now - me.get("last_boost", 0)) > (4 * 3600):
        me["last_boost"] = now
        income = calculate_income_per_hour(me)
        me["gold"] += income
        return web.json_response({"success": True, "msg": f"Бустер активирован! Вы получили {income} золота."})
    return web.json_response({"success": False, "error": "Кулдаун 4 часа!"})

async def handle_buy_item(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    item_type = data.get("item")
    if not user_id or user_id not in users: return web.json_response({"success": False})
    
    me = users[user_id]
    now = time.time()
    
    if item_type == "shield":
        if me["shield_until"] > now: return web.json_response({"success": False, "error": "Щит уже активен!"})
        if me["crystals"] < 15: return web.json_response({"success": False, "error": "Нужно 15 💎"})
        me["crystals"] -= 15
        me["shield_until"] = now + 10800 # 3 часа
        return web.json_response({"success": True, "msg": "Щит активирован на 3 часа!"})
        
    elif item_type == "chains":
        if me["chains_until"] > now: return web.json_response({"success": False, "error": "Цепи уже активны!"})
        if me["crystals"] < 20: return web.json_response({"success": False, "error": "Нужно 20 💎"})
        me["crystals"] -= 20
        me["chains_until"] = now + 43200 # 12 часов
        return web.json_response({"success": True, "msg": "Цепи накинуты на ваших рабов на 12 часов!"})
        
    return web.json_response({"success": False})

async def handle_buy(request):
    data = await request.json()
    buyer_id = get_user_id_from_request(request) or data.get("user_id")
    target_id = str(data.get("target_id"))
    
    if not buyer_id or buyer_id not in users: return web.json_response({"success": False, "error": "Auth error"})
    if target_id not in users: return web.json_response({"success": False, "error": "Игрок не найден"})
    
    buyer = users[buyer_id]
    target = users[target_id]
    now = time.time()
    
    if target["owner_id"]: return web.json_response({"success": False, "error": "Уже куплен!"})
    if target.get("shield_until", 0) > now: return web.json_response({"success": False, "error": "У игрока Щит!"})
    if buyer_id == target_id: return web.json_response({"success": False, "error": "Нельзя себя!"})
    
    price = 1000 + (len(target["name"]) * 10)
    if buyer["gold"] < price: return web.json_response({"success": False, "error": "Мало золота!"})

    update_income_before_change(buyer)
    
    buyer["gold"] -= price
    target["owner_id"] = buyer_id
    buyer["bought_count"] += 1
    target["sold_count"] += 1
    
    update_income_before_change(buyer) # Пересчет дохода после покупки

    try: await bot.send_message(int(target_id), f"😡 Вас купил {buyer['name']}! Выкупите себя за {price}💰.")
    except: pass

    return web.json_response({"success": True})

async def handle_redeem(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    if not user_id or user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    now = time.time()
    
    if not me["owner_id"]: return web.json_response({"success": False, "error": "Вы свободны!"})
    if me["chains_until"] > now: return web.json_response({"success": False, "error": "На вас надеты цепи! Ждите."})

    price = 1000 + (len(me["name"]) * 10)
    if me["gold"] < price: return web.json_response({"success": False, "error": f"Нужно {price}💰"})

    update_income_before_change(me)
    me["gold"] -= price
    me["owner_id"] = None
    return web.json_response({"success": True})

async def handle_open_case(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    if not user_id or user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    
    if me["crystals"] < 25: return web.json_response({"success": False, "error": "Нужно 25 💎!"})
    
    me["crystals"] -= 25
    total_weight = sum(item["weight"] for item in CASE_LOOT)
    rand_val = random.uniform(0, total_weight)
    current_weight = 0
    selected_loot = CASE_LOOT[0]
    
    for item in CASE_LOOT:
        current_weight += item["weight"]
        if rand_val <= current_weight: selected_loot = item; break
        
    loot_msg = selected_loot["msg"]
    loot_type = selected_loot["type"]
    
    if loot_type == "gold": me["gold"] += selected_loot["value"]
    elif loot_type == "income_10h":
        income = calculate_income_per_hour(me)
        me["gold"] += income * 10 if income > 0 else 500
    elif loot_type == "frame":
        if selected_loot["value"] not in me["inventory"]: me["inventory"].append(selected_loot["value"])
    elif loot_type == "avatar":
        if selected_loot["value"] not in me["inventory"]: me["inventory"].append(selected_loot["value"])
    elif loot_type == "item":
        if selected_loot["value"] == "shield": me["shield_until"] = time.time() + 10800
        elif selected_loot["value"] == "chains": me["chains_until"] = time.time() + 43200
    elif loot_type == "npc":
        if npcs["npc_dragon"]["owner_id"] is None:
            npcs["npc_dragon"]["owner_id"] = user_id
            update_income_before_change(me)
        else:
            me["gold"] += 15000
            loot_msg = "Дракон занят. Компенсация 15 000 золота!"
            
    return web.json_response({"success": True, "msg": loot_msg, "win_item": selected_loot, "all_loot": CASE_LOOT})

async def handle_buy_avatar(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    avatar = data.get("avatar")
    if user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    
    if avatar in me["inventory"]: return web.json_response({"success": False, "error": "Уже есть!"})
    
    prices = {"avatar_2": 100, "avatar_3": 150}
    if avatar not in prices: return web.json_response({"success": False})
    
    if me["crystals"] < prices[avatar]: return web.json_response({"success": False, "error": "Мало кристаллов!"})
    me["crystals"] -= prices[avatar]
    me["inventory"].append(avatar)
    return web.json_response({"success": True, "msg": "Аватарка куплена!"})

async def handle_buy_frame(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    frame = data.get("frame")
    if user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    
    if frame in me["inventory"]: return web.json_response({"success": False, "error": "Уже есть!"})
    
    prices = {"frame_gold": 50, "frame_blood": 25000}
    currency = data.get("currency")
    
    if frame not in prices: return web.json_response({"success": False})
    
    if currency == "crystals":
        if me["crystals"] < prices[frame]: return web.json_response({"success": False, "error": "Мало 💎"})
        me["crystals"] -= prices[frame]
    else:
        if me["gold"] < prices[frame]: return web.json_response({"success": False, "error": "Мало 💰"})
        me["gold"] -= prices[frame]
        
    me["inventory"].append(frame)
    return web.json_response({"success": True, "msg": "Рамка куплена!"})

async def handle_equip_frame(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    frame = data.get("frame")
    if user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    if frame in me["inventory"] or frame == "frame_basic":
        me["frame"] = frame
        return web.json_response({"success": True, "msg": "Рамка надета!"})
    return web.json_response({"success": False})

async def handle_equip_avatar(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    avatar = data.get("avatar")
    if user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    if avatar in me["inventory"] or avatar == "avatar_1":
        me["avatar"] = avatar
        return web.json_response({"success": True, "msg": "Аватарка надета!"})
    return web.json_response({"success": False})

async def handle_change_color(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    color = data.get("color")
    if user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    if me["crystals"] < 5: return web.json_response({"success": False, "error": "Нужно 5 💎"})
    me["crystals"] -= 5
    me["name_color"] = color
    return web.json_response({"success": True, "msg": "Цвет изменен!"})

async def handle_daily(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    if user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    if time.time() - me["last_daily"] > 86400:
        me["gold"] += 500
        me["last_daily"] = time.time()
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Уже забирали!"})

async def handle_watch_ad(request):
    data = await request.json()
    user_id = get_user_id_from_request(request) or data.get("user_id")
    if user_id not in users: return web.json_response({"success": False})
    me = users[user_id]
    if time.time() - me["last_ad_watch"] > 3600:
        me["gold"] += 250
        me["last_ad_watch"] = time.time()
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "Ждите час!"})

async def handle_get_refs(request):
    user_id = get_user_id_from_request(request) or request.query.get("user_id")
    if user_id not in users: return web.json_response({"refs": []})
    
    refs = []
    for uid, u in users.items():
        if u.get("referrer_id") == user_id:
            refs.append({"id": uid, "name": u["name"], "game_id": u["game_id"], "is_star": u.get("is_star", False)})
    return web.json_response({"refs": refs})

async def handle_event_info(request):
    user_id = get_user_id_from_request(request) or request.query.get("user_id")
    
    all_participants = [
        {"name": u["name"], "count": u.get("event_ref_count", 0), "is_star": u.get("is_star", False), "id": uid}
        for uid, u in users.items() if u.get("event_ref_count", 0) > 0
    ]
    all_participants.sort(key=lambda x: x["count"], reverse=True)
    
    my_place = 0
    my_count = 0
    if user_id in users:
        my_count = users[user_id].get("event_ref_count", 0)
        for i, p in enumerate(all_participants):
            if p["id"] == user_id: my_place = i + 1; break

    rewards = [
        {"place": "1 место", "reward": "Дракон 🐉, 1000 💎, Аватарка, Рамка, Золотой ник", "icon": "🥇"},
        {"place": "2-3 место", "reward": "500 💎, Аватарка 'Рыцарь', Статус Звезды ⭐", "icon": "🥈"},
        {"place": "4-10 место", "reward": "200 💎", "icon": "🎖"}
    ]
    return web.json_response({"top": all_participants[:25], "rewards": rewards, "my_place": my_place, "my_count": my_count})

# --- ФОНОВАЯ ЗАДАЧА ДЛЯ ИВЕНТА ---
async def background_event_checker():
    global EVENT_ENDED
    await asyncio.sleep(5)
    while True:
        now = time.time()
        if (now - SERVER_START_TIME) >= EVENT_DURATION and not EVENT_ENDED:
            EVENT_ENDED = True
            top_refs = sorted(users.values(), key=lambda x: x.get("event_ref_count", 0), reverse=True)[:10]
            for i, u in enumerate(top_refs):
                if u.get("event_ref_count", 0) > 0:
                    if i == 0:
                        u["crystals"] += 1000
                        u["is_star"] = True
                        u["name_color"] = "#ffd700"
                        npcs["npc_dragon"]["owner_id"] = u["tg_id"]
                    elif i < 3:
                        u["crystals"] += 500
                        u["is_star"] = True
                    else:
                        u["crystals"] += 200
        await asyncio.sleep(60)

async def main():
    asyncio.create_task(background_event_checker())
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/app', handle_index)
    app.router.add_get('/api/state', handle_state)
    app.router.add_post('/api/work', handle_work)
    app.router.add_post('/api/collect', handle_collect)
    app.router.add_post('/api/boost', handle_boost)
    app.router.add_post('/api/buy_item', handle_buy_item)
    app.router.add_post('/api/buy', handle_buy)
    app.router.add_post('/api/redeem', handle_redeem)
    app.router.add_post('/api/open_case', handle_open_case)
    app.router.add_post('/api/buy_avatar', handle_buy_avatar)
    app.router.add_post('/api/buy_frame', handle_buy_frame)
    app.router.add_post('/api/equip_frame', handle_equip_frame)
    app.router.add_post('/api/equip_avatar', handle_equip_avatar)
    app.router.add_post('/api/change_color', handle_change_color)
    app.router.add_post('/api/daily', handle_daily)
    app.router.add_post('/api/watch_ad', handle_watch_ad)
    app.router.add_get('/api/refs', handle_get_refs)
    app.router.add_get('/api/event_info', handle_event_info)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"✅ Royal Empire Server started on {PORT}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
