from aiogram import Bot, Dispatcher, executor, types
import json, random, os, asyncio
from datetime import datetime, timedelta

# ======================
# НАСТРОЙКА
# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # в Render добавить в Environment Variables
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

PROGRESS_FILE = "progress.json"
DATE_FMT = "%Y-%m-%d"
ADMIN_ID = 288158839  # твой chat_id

# ======================
# УТИЛИТЫ
# ======================
def today_str():
    return datetime.now().strftime(DATE_FMT)

def is_due(date_str: str):
    if not date_str:
        return False
    try:
        d = datetime.strptime(date_str, DATE_FMT).date()
    except Exception:
        return False
    return datetime.now().date() >= d

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def split_text(text, limit=3500):
    return [text[i:i + limit] for i in range(0, len(text), limit)]

# ======================
# ДАННЫЕ
# ======================
progress = load_progress()

with open("questions.json", encoding="utf-8") as f:
    questions = json.load(f)

Q_BY_ID = {int(q["id"]): q for q in questions}
TOPICS = sorted(set(q["topic"] for q in questions))

# ======================
# ВСПОМОГАТЕЛЬНОЕ
# ======================
def get_user(uid: str, name_hint="Без имени"):
    u = progress.setdefault(uid, {
        "name": name_hint,
        "cards": {},           # "qid_str": {"interval": int, "next_review": "YYYY-MM-DD"}
        "topics": {},          # "topic": {"correct": int, "total": int}
        "streak": 0,
        "last_goal_day": None,
        "last_review": None,
        "goal_per_day": 10,
        "done_today": 0,
        "last_day": today_str()
    })
    # сброс done_today при смене даты
    if u.get("last_day") != today_str():
        u["done_today"] = 0
        u["last_day"] = today_str()
    return u

async def send_question(chat_id: int, topic_filter: str = None):
    uid = str(chat_id)
    u = get_user(uid)
    cards = u.get("cards", {})

    # 1) К повтору
    due_ids = []
    for qid_str, meta in cards.items():
        if is_due(meta.get("next_review")):
            qid = int(qid_str)
            if topic_filter and Q_BY_ID.get(qid, {}).get("topic") != topic_filter:
                continue
            due_ids.append(qid)

    if due_ids:
        qid = random.choice(due_ids)
        return await send_question_text(chat_id, Q_BY_ID[qid])

    # 2) Новые
    done_ids = {int(k) for k in cards.keys()}
    pool = [q for q in questions if int(q["id"]) not in done_ids]
    if topic_filter:
        pool = [q for q in pool if q.get("topic") == topic_filter]

    if not pool:
        await bot.send_message(chat_id, "🎉 Все вопросы пройдены или запланированы на повтор.")
        return
    q = random.choice(pool)
    await send_question_text(chat_id, q)

async def send_question_text(chat_id: int, q: dict):
    qid = int(q["id"])
    topic = q.get("topic", "Вопрос")
    text = f"🧠 {topic}\n\n{q['question']}\n\n" + "\n".join(
        f"{i+1}) {opt}" for i, opt in enumerate(q["options"])
    )
    kb = types.InlineKeyboardMarkup(row_width=3)
    for i in range(len(q["options"])):
        kb.insert(types.InlineKeyboardButton(str(i + 1), callback_data=f"a:{qid}:{i+1}"))
    kb.add(types.InlineKeyboardButton("⏭ Далее", callback_data="next"))
    await bot.send_message(chat_id, text, reply_markup=kb)

def update_interval(card: dict, correct: bool):
    # Простая SM-логика: удвоение интервала при верном ответе, сброс на 1 при ошибке
    if correct:
        card["interval"] = min(max(1, card.get("interval", 1)) * 2, 60)
        next_day = datetime.now() + timedelta(days=card["interval"])
    else:
        card["interval"] = 1
        next_day = datetime.now() + timedelta(days=1)
    card["next_review"] = next_day.strftime(DATE_FMT)
    return card

# ======================
# /start
# ======================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    uid = str(message.chat.id)
    uname = message.from_user.first_name or "Без имени"
    get_user(uid, uname)
    save_progress(progress)

    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("⏭ Начать", callback_data="next"))
    await message.answer(
        f"👋 Привет, {uname}!\n"
        "Этот бот учит педиатрию с интервальным повторением.\n\n"
        "💡 Ошибки повторяются завтра, верные ответы — через 2, 4, 8 и т.д. дней.\n"
        "🎯 Ежедневная цель по умолчанию: 10 карточек (измени через /goal 15)\n\n"
        "💬 We are what we repeatedly do. Excellence, then, is not an act, but a habit.\n\n"
        "Смотри /help.",
        reply_markup=kb
    )

# ======================
# /help
# ======================
@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    await message.answer(
        "🧭 Команды:\n"
        "/train — выбрать тему\n"
        "/review — повтор карточек на сегодня\n"
        "/stats — статистика\n"
        "/goal N — цель на день (напр. /goal 20)\n"
        "/reset_topic — сброс прогресса по теме\n"
        "/reset — полный сброс\n"
    )

# ======================
# /goal
# ======================
@dp.message_handler(commands=["goal"])
async def set_goal(message: types.Message):
    uid = str(message.chat.id)
    u = get_user(uid)
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.answer("Формат: /goal 15 — сколько карточек в день.")
    goal = int(parts[1])
    u["goal_per_day"] = max(1, goal)
    save_progress(progress)
    await message.answer(f"🎯 Новая ежедневная цель: {u['goal_per_day']}.")

# ======================
# /train
# ======================
@dp.message_handler(commands=["train"])
async def choose_topic(message: types.Message):
    if not TOPICS:
        return await message.answer("Пока нет тем.")
    kb = types.InlineKeyboardMarkup(row_width=2)
    for t in TOPICS:
        kb.insert(types.InlineKeyboardButton(t, callback_data=f"train_{t}"))
    await message.answer("🎯 Выбери тему для тренировки:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("train_"))
async def train_topic(callback_query: types.CallbackQuery):
    await callback_query.answer()
    topic = callback_query.data.replace("train_", "", 1)
    uid = str(callback_query.from_user.id)
    await bot.send_message(callback_query.from_user.id, f"📚 Тема: {topic}")
    await send_question(callback_query.from_user.id, topic_filter=topic)

# ======================
# /review
# ======================
@dp.message_handler(commands=["review"])
async def review_today(message: types.Message):
    uid = str(message.chat.id)
    u = get_user(uid)
    due = [int(qid) for qid, meta in u.get("cards", {}).items() if is_due(meta.get("next_review"))]
    if not due:
        return await message.answer("✅ На сегодня нет карточек к повтору.")
    await message.answer(f"📘 Сегодня к повтору: {len(due)}.")
    qid = random.choice(due)
    await send_question_text(message.chat.id, Q_BY_ID[qid])

# ======================
# Ответы на варианты и «Далее»
# ======================
@dp.callback_query_handler(lambda c: c.data == "next")
async def next_card(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await send_question(callback_query.from_user.id)

@dp.callback_query_handler(lambda c: c.data.startswith("a:"))
async def handle_answer(callback_query: types.CallbackQuery):
    await callback_query.answer()
    uid = str(callback_query.from_user.id)
    u = get_user(uid)

    # парсинг "a:<qid>:<optnum>"
    try:
        _, qid_str, opt_str = callback_query.data.split(":")
        qid = int(qid_str)
        chosen_idx = int(opt_str) - 1
    except Exception:
        return

    q = Q_BY_ID.get(qid)
    if not q:
        return

    correct = (chosen_idx == q["correct_index"])

    # обновляем карточку
    cards = u.setdefault("cards", {})
    card = cards.get(qid_str, {"interval": 1, "next_review": today_str()})
    card = update_interval(card, correct)
    cards[qid_str] = card

    # топики
    topic = q.get("topic", "Без темы")
    tdata = u.setdefault("topics", {}).setdefault(topic, {"correct": 0, "total": 0})
    tdata["total"] += 1
    if correct:
        tdata["correct"] += 1

    # дневная цель / streak
    u["last_review"] = today_str()
    if u.get("last_day") != today_str():
        u["done_today"] = 0
        u["last_day"] = today_str()
    u["done_today"] = u.get("done_today", 0) + 1
    goal = u.get("goal_per_day", 10)
    if u["done_today"] >= goal and u.get("last_goal_day") != today_str():
        u["streak"] = u.get("streak", 0) + 1
        u["last_goal_day"] = today_str()

    save_progress(progress)

    status = "✅ Верно!" if correct else "❌ Неверно."
    explanation = q.get("explanation", "").strip()
    full_text = f"{status}\n\n{explanation}" if explanation else status
    for part in split_text(full_text, 3000):
        await bot.send_message(uid, part)

    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("⏭ Далее", callback_data="next"))
    await bot.send_message(uid, "➡️ Продолжим?", reply_markup=kb)

# ======================
# /stats
# ======================
@dp.message_handler(commands=["stats"])
async def stats(message: types.Message):
    uid = str(message.chat.id)
    u = get_user(uid)
    total = len(u.get("cards", {}))
    due = sum(1 for meta in u.get("cards", {}).values() if is_due(meta.get("next_review")))
    goal = u.get("goal_per_day", 10)
    done = u.get("done_today", 0)
    streak = u.get("streak", 0)
    total_correct = sum(t["correct"] for t in u.get("topics", {}).values())
    total_answers = sum(t["total"] for t in u.get("topics", {}).values())
    acc = round(100 * total_correct / total_answers) if total_answers else 0

    msg = (
        f"🎯 Цель: {goal} в день\n"
        f"📊 Сегодня: {done}/{goal}\n"
        f"🔥 Серия: {streak} дней\n"
        f"📘 Всего карточек: {total}\n"
        f"📅 К повтору: {due}\n"
        f"💯 Точность: {acc}%"
    )
    await message.answer(msg)

# ======================
# /reset_topic и /reset
# ======================
@dp.message_handler(commands=["reset_topic"])
async def reset_topic(message: types.Message):
    if not TOPICS:
        return await message.answer("Пока нет тем.")
    kb = types.InlineKeyboardMarkup(row_width=2)
    for t in TOPICS:
        kb.insert(types.InlineKeyboardButton(t, callback_data=f"reset_{t}"))
    await message.answer("Выбери тему для сброса:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("reset_"))
async def do_reset_topic(callback_query: types.CallbackQuery):
    await callback_query.answer()
    topic = callback_query.data.replace("reset_", "", 1)
    uid = str(callback_query.from_user.id)
    u = get_user(uid)
    to_del = [qid for qid, obj in Q_BY_ID.items() if obj.get("topic") == topic]
    for qid in to_del:
        u["cards"].pop(str(qid), None)
    save_progress(progress)
    await bot.send_message(uid, f"♻️ Сбросили прогресс по теме «{topic}».")

@dp.message_handler(commands=["reset"])
async def reset_all(message: types.Message):
    uid = str(message.chat.id)
    uname = message.from_user.first_name or "Без имени"
    progress[uid] = {
        "name": uname,
        "cards": {},
        "topics": {},
        "streak": 0,
        "last_goal_day": None,
        "last_review": None,
        "goal_per_day": 10,
        "done_today": 0,
        "last_day": today_str()
    }
    save_progress(progress)
    await message.answer("🔄 Полный сброс. Начинай с /start или /train.")

# ======================
# Установка команд в меню
# ======================
async def set_commands():
    cmds = [
        types.BotCommand("start", "Начать"),
        types.BotCommand("help", "Помощь"),
        types.BotCommand("train", "Выбор темы"),
        types.BotCommand("review", "Повтор на сегодня"),
        types.BotCommand("stats", "Статистика"),
        types.BotCommand("goal", "Цель на день"),
        types.BotCommand("reset_topic", "Сброс темы"),
        types.BotCommand("reset", "Полный сброс"),
    ]
    await bot.set_my_commands(cmds)

# ======================
# ЗАПУСК (Render: Flask + polling)
# ======================
if __name__ == "__main__":
    print("✅ Бот запущен и ждёт сообщений в Telegram...")

    # поднимаем Flask keep-alive на 10000 порту
    import threading
    from server import app
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000), daemon=True).start()

    # ставим команды и запускаем polling
    loop = asyncio.get_event_loop()
    loop.create_task(set_commands())
    executor.start_polling(dp, skip_updates=True)