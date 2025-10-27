from aiogram import Bot, Dispatcher, executor, types
import json, random, os, asyncio
from datetime import datetime, timedelta

# === НАСТРОЙКА ===
bot = Bot(token=os.getenv("BOT_TOKEN"))  # Токен берётся из переменной окружения
dp = Dispatcher(bot)
PROGRESS_FILE = "progress.json"
DATE_FMT = "%Y-%m-%d"
ADMIN_ID = 288158839  # твой chat_id

# === УТИЛИТЫ ===
def today():
    return datetime.now().strftime(DATE_FMT)

def is_due(date_str):
    if not date_str:
        return False
    try:
        date = datetime.strptime(date_str, DATE_FMT).date()
    except Exception:
        return False
    return datetime.now().date() >= date

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

# === МОТИВАЦИОННЫЕ ЦИТАТЫ ===
QUOTES = [
    "We are what we repeatedly do. Excellence, then, is not an act, but a habit. – Aristotle",
    "Discipline equals freedom. – Jocko Willink",
    "Medicine is mostly controlled curiosity.",
    "Без повторения нет мастерства.",
    "Tiny progress every day beats occasional bursts.",
    "Устойчивость – лучший вид таланта.",
    "Half of medicine is patience. The other half is coffee.",
    "Practice turns chaos into instinct.",
    "The best doctors never stop being students.",
    "Ты сегодня на шаг ближе к автоматическим ответам."
]

# === ДОСТИЖЕНИЯ ===
ACHIEVEMENTS = {
    1: "👶 Первый вдох",
    2: "👣 Первые шаги",
    3: "🎯 Ординатор-энтузиаст",
    5: "⚡️ Мозговая активация",
    7: "💪 Гигант педиатр",
    10: "🌊 Врач на волне",
    14: "☕️ Доктор без выходных",
    21: "🩺 Стабильность – признак профи",
    30: "📚 Гуру гайдлайнов",
    60: "🏅 Наставник ординаторов",
    90: "💎 Легендарный неонатолог",
    180: "🔥 Кандидат бессмертия",
    365: "👑 Легенда отделения"
}

# === ДАННЫЕ ===
progress = load_progress()
with open("questions.json", encoding="utf-8") as f:
    questions = json.load(f)
Q_BY_ID = {int(q["id"]): q for q in questions}
TOPICS = sorted(set(q["topic"] for q in questions))

# === СТАРТ ===
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    uid = str(message.chat.id)
    uname = message.from_user.first_name or "Без имени"
    progress.setdefault(uid, {
        "name": uname,
        "cards": {},
        "topics": {},
        "streak": 0,
        "last_review": None,
        "goal_per_day": 10,
        "done_today": 0
    })
    save_progress(progress)
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("⏭ Начать", callback_data="next"))
    await message.answer(
        f"👋 Привет, {uname}!\n"
        "Этот бот помогает учить педиатрию с интервальным повторением.\n\n"
        "💡 Ошибки повторяются завтра, правильные – через 2, 4, 8 и т.д. дней.\n"
        "🎯 Ежедневная цель: 10 карточек (можно поменять через /goal 15)\n\n"
        "💬 We are what we repeatedly do. Excellence, then, is not an act, but a habit.\n\n"
        "Посмотри /help, чтобы узнать команды.",
        reply_markup=kb
    )

# === HELP ===
@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    await message.answer(
        "🧭 Команды:\n"
        "/train – выбрать тему\n"
        "/review – повтор карточек на сегодня\n"
        "/stats – статистика и прогресс\n"
        "/leaderboard – рейтинг пользователей\n"
        "/goal N – установить цель (например, /goal 20)\n"
        "/reset_topic – сброс темы\n"
        "/reset – полный сброс\n"
    )

# === УСТАНОВКА ЦЕЛИ ===
@dp.message_handler(commands=["goal"])
async def set_goal(message: types.Message):
    uid = str(message.chat.id)
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.answer("Используй формат: /goal 15 (число карточек в день).")
    goal = int(parts[1])
    udata = progress.setdefault(uid, {})
    udata["goal_per_day"] = goal
    save_progress(progress)
    await message.answer(f"🎯 Новая ежедневная цель: {goal} карточек.")

# === ТРЕНИРОВКА ===
@dp.message_handler(commands=["train"])
async def choose_topic(message: types.Message):
    kb = types.InlineKeyboardMarkup(row_width=2)
    for t in TOPICS:
        kb.insert(types.InlineKeyboardButton(t, callback_data=f"train_{t}"))
    await message.answer("🎯 Выбери тему для тренировки:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("train_"))
async def train_topic(callback_query: types.CallbackQuery):
    await callback_query.answer()
    topic = callback_query.data.split("train_")[1]
    uid = str(callback_query.from_user.id)
    questions_in_topic = [q for q in questions if q["topic"] == topic]

    if not questions_in_topic:
        await bot.send_message(uid, f"❌ В теме «{topic}» пока нет вопросов.")
        return

    q = random.choice(questions_in_topic)
    await send_question_text(uid, q)


# === ВОПРОСЫ И ОТВЕТЫ ===
async def send_question_text(chat_id, q):
    qid = int(q["id"])
    text = f"🧠 {q.get('topic', 'Вопрос')}\n\n{q['question']}\n\n" + "\n".join(
        f"{i+1}) {opt}" for i, opt in enumerate(q["options"])
    )
    kb = types.InlineKeyboardMarkup(row_width=3)
    for i in range(len(q["options"])):
        kb.insert(types.InlineKeyboardButton(str(i + 1), callback_data=f"a:{qid}:{i+1}"))
    kb.add(types.InlineKeyboardButton("⏭ Далее", callback_data="next"))
    await bot.send_message(chat_id, text, reply_markup=kb)


# === КНОПКА "Далее" ===
@dp.callback_query_handler(lambda c: c.data == "next")
async def next_card(callback_query: types.CallbackQuery):
    await callback_query.answer()
    uid = str(callback_query.from_user.id)
    uname = progress.get(uid, {}).get("name", "Без имени")
    await bot.send_message(uid, f"💪 Отлично, {uname}! Выбери /train или /review, чтобы продолжить.")


# === ЗАПУСК ===
if __name__ == "__main__":
    print("✅ Бот запущен и ждёт сообщений в Telegram...")
    loop = asyncio.get_event_loop()
    loop.create_task(set_commands())

    # Flask keep-alive сервер
    import threading
    from server import app
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000)).start()

    executor.start_polling(dp)