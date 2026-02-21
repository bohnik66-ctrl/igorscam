import asyncio, re
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

# -------------------- Настройки --------------------
api_id = 31283527         # вставь свой api_id
api_hash = "a9bfac04e79550b7edc2b1aa4f612959"  # твой API HASH
client = TelegramClient("session", api_id, api_hash)

DB_CHAT = -5038963258       # чат с общей базой
QUEUE_CHAT = -5207389598    # чат очереди сообщений
price = 950                 # стартовая цена

TEXT = """привет, я скупаю нфт для крафта, давай я заберу нфт подарок за {price} через гаранта что бы КД не было и без комисии

Если не интересует просто удали пожалуйста чат у обоих, не кидай в ЧС, все честно, отзывы в профиле, спасибо!"""

sent_users = set()          # локальная база тех, кому уже писал
answered_users = {}         # пользователи, которые ответили

# -------------------- Очистка очереди --------------------
async def clear_queue():
    """Очищает старые сообщения из QUEUE_CHAT при старте"""
    try:
        async for msg in client.iter_messages(QUEUE_CHAT, limit=100):
            await msg.delete()
        print("🧹 Очередь очищена")
    except Exception as e:
        print(f"⚠️ Не удалось очистить очередь: {e}")

# -------------------- Синхронизация локальной истории --------------------
async def sync_local_history():
    """Синхронизируем все приватные чаты с общей базой"""
    print("🔄 Синхронизация локальной истории с базой DB_CHAT...")

    existing_ids = set()
    try:
        async for msg in client.iter_messages(DB_CHAT, limit=None):
            if not msg.text:
                continue
            if msg.text.startswith("#DB"):
                try:
                    line = msg.text.split("\n")[1]
                    user_id = int(line.split("|")[0].strip())
                    existing_ids.add(user_id)
                except:
                    continue
    except Exception as e:
        print(f"⚠️ Не удалось загрузить DB_CHAT: {e}")

    added_count = 0
    async for dialog in client.iter_dialogs():
        if not dialog.is_user:
            continue
        try:
            user = await client.get_entity(dialog.id)
            if user.id not in existing_ids:
                await client.send_message(DB_CHAT, f"#DB\n{user.id} | @{user.username or 'no_username'}")
                existing_ids.add(user.id)
                added_count += 1
        except Exception as e:
            print(f"⚠️ Не удалось обработать {dialog.name}: {e}")

    print(f"✅ Синхронизация завершена. Добавлено {added_count} пользователей в DB_CHAT")

# -------------------- Загрузка базы --------------------
async def load_db():
    global sent_users
    sent_users = set()
    try:
        async for msg in client.iter_messages(DB_CHAT, limit=None):
            if not msg.text:
                continue
            if msg.text.startswith("#DB"):
                try:
                    line = msg.text.split("\n")[1]
                    user_id = int(line.split("|")[0].strip())
                    sent_users.add(user_id)
                except:
                    continue
    except Exception as e:
        print(f"⚠️ Не удалось загрузить DB_CHAT: {e}")

    print(f"✅ Загружено {len(sent_users)} пользователей, кому уже писал")

# -------------------- Сохранение в базу --------------------
async def save_to_db(user):
    try:
        await client.send_message(DB_CHAT, f"#DB\n{user.id} | @{user.username or 'no_username'}")
    except Exception as e:
        print(f"⚠️ Не удалось сохранить {user.username} в DB_CHAT: {e}")
    sent_users.add(user.id)

# -------------------- Добавление в очередь --------------------
async def add_to_queue(usernames, chat_id):
    for username in usernames:
        await client.send_message(QUEUE_CHAT, f"#QUEUE\n{username} | {chat_id}")
        try:
            user = await client.get_entity(username.strip())
            if user.id not in sent_users:
                await client.send_message(DB_CHAT, f"#DB\n{user.id} | @{user.username or 'no_username'}")
                sent_users.add(user.id)
        except Exception as e:
            print(f"⚠️ Не удалось добавить {username} в базу: {e}")

# -------------------- Обработка очереди --------------------
async def process_queue():
    while True:
        async for msg in client.iter_messages(QUEUE_CHAT, limit=20):
            if not msg.text or not msg.text.startswith("#QUEUE"):
                continue
            try:
                username, orig_chat = msg.text.split("\n")[1].split("|")
                orig_chat = int(orig_chat.strip())
            except:
                continue

            try:
                user = await client.get_entity(username.strip())
                if user.id in sent_users:
                    await msg.delete()
                    continue

                sent = False
                while not sent:
                    try:
                        await client.send_message(user, TEXT.format(price=price))
                        sent = True
                    except FloodWaitError as e:
                        print(f"⏳ Flood wait {e.seconds} сек")
                        await asyncio.sleep(e.seconds)

                await save_to_db(user)
                await msg.delete()
                await client.send_message(orig_chat, f"✅ Написал {username}")
                await asyncio.sleep(30)

            except Exception as e:
                await client.send_message(orig_chat, f"❌ Ошибка {username}: {e}")
                await asyncio.sleep(30)
        await asyncio.sleep(5)

# -------------------- Команды --------------------
@client.on(events.NewMessage(outgoing=True, pattern=r"/price (\d+)"))
async def set_price(event):
    global price
    price = int(event.pattern_match.group(1))
    await event.reply(f"💰 Новая цена: {price}")

@client.on(events.NewMessage(outgoing=True, pattern="/send"))
async def send_messages(event):
    if not event.is_reply:
        await event.reply("❗ Ответь на сообщение с юзерами")
        return
    msg = await event.get_reply_message()
    users = re.findall(r"@[\w\d_]{4,}", msg.text)
    if not users:
        await event.reply("❌ Юзернеймы не найдены")
        return
    await event.reply(f"👀 Добавлено {len(users)} в очередь")
    await add_to_queue(users, event.chat_id)

@client.on(events.NewMessage(outgoing=True, pattern="/answers"))
async def show_answers(event):
    if not answered_users:
        await event.reply("❌ Ответов пока нет")
        return
    text = "📨 Ответившие:\n"
    for u in answered_users.values():
        text += f"• {u}\n"
    await event.reply(text)

# -------------------- Отслеживание ответов --------------------
@client.on(events.NewMessage(incoming=True))
async def catch_answers(event):
    if not event.is_private:
        return
    user = await event.get_sender()
    if user.bot:
        return
    if user.id not in answered_users:
        answered_users[user.id] = user.username or user.first_name
        try:
            await client.send_message(DB_CHAT, f"#ANSWER\n{user.id} | @{user.username or 'no_username'}")
        except:
            pass

# -------------------- Старт --------------------
async def main():
    await client.start()
    print("✅ Юзербот запущен")

    # Очистка очереди перед обработкой
    await clear_queue()

    # Синхронизация DB_CHAT и локальной истории
    await sync_local_history()
    await load_db()

    # Запуск основного цикла обработки
    asyncio.create_task(process_queue())
    await client.run_until_disconnected()

asyncio.run(main())
