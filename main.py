# ... (начало файла main.py без изменений) ...

# Добавь эту функцию перед main()
async def handle_user_info(request):
    target_id = request.query.get("target_id")
    if not target_id: return web.json_response({"error": "No ID"}, status=400)

    target_user = users.get(target_id)
    if not target_user: return web.json_response({"error": "Игрок не найден"}, status=404)

    all_entities = {**users, **npcs}
    
    # Считаем доход и рабов для этого игрока
    target_income = 0
    target_slaves = []
    
    for uid, u in all_entities.items():
        if u["owner_id"] == target_id:
            if u.get("is_npc"):
                inc = u["base_income"] * u["level"]
                target_slaves.append({"id": uid, "name": u["name"], "rarity": u["rarity"], "income": inc, "is_npc": True})
            else:
                inc = 50
                target_slaves.append({"id": uid, "name": u["name"], "rarity": "Игрок", "income": inc, "is_npc": False})
            target_income += inc

    # Узнаем, кто владелец этого игрока (если есть)
    target_owner_name = None
    if target_user["owner_id"] and target_user["owner_id"] in all_entities:
        target_owner_name = all_entities[target_user["owner_id"]]["name"]

    return web.json_response({
        "name": target_user["name"],
        "gold": target_user["gold"],
        "income": target_income,
        "slaves": target_slaves,
        "owner_name": target_owner_name,
        "id": target_id
    })

async def main():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/app', handle_index)
    app.router.add_get('/api/state', handle_state)
    
    # НОВЫЙ РОУТ ДЛЯ ПРОФИЛЯ
    app.router.add_get('/api/user_info', handle_user_info) 
    
    app.router.add_post('/api/work', handle_work)
    app.router.add_post('/api/collect', handle_collect)
    app.router.add_post('/api/daily', handle_daily)
    app.router.add_post('/api/buy', handle_buy)
    app.router.add_post('/api/upgrade', handle_upgrade)
    app.router.add_post('/api/admin_cheat', handle_admin_cheat)
    app.router.add_post('/api/watch_ad', handle_watch_ad)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    print(f"✅ Сервер запущен на порту {PORT}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
