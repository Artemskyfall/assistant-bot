import os
import json
import asyncio
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiohttp import ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MEMORY_FILE = "memory.json"  # здесь бот хранит память

SYSTEM_PROMPT = """
Ты — личный компаньон и ассистент пользователя.
Общайся тепло, дружелюбно, по-человечески.
Помогай с делами, планированием, мыслями.
Помни, что вы обсуждали раньше, учитывай задачи, заметки и события пользователя.
Говори по-русски, простым языком.
"""

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ================= ПАМЯТЬ ================= #

def load_memory() -> Dict[str, Any]:
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_memory(data: Dict[str, Any]) -> None:
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

memory: Dict[str, Any] = load_memory()

def get_user_state(user_id: int) -> Dict[str, Any]:
    uid = str(user_id)
    if uid not in memory:
        memory[uid] = {
            "history": [],
            "tasks": [],
            "notes": [],
            "reminders": [],
        }
    state = memory[uid]
    state.setdefault("history", [])
    state.setdefault("tasks", [])
    state.setdefault("notes", [])
    state.setdefault("reminders", [])
    return state

# ================= LLM ================= #

async def ask_llm(user_id: int, user_text: str) -> str:
    state = get_user_state(user_id)
    history: List[Dict[str, str]] = state["history"]

    history.append({"role": "user", "content": user_text})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-12:]

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",  # при желании можно заменить на "gpt-5.1"
        "messages": messages,
    }

    async with ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            try:
                reply_text = data["choices"][0]["message"]["content"]
            except Exception:
                reply_text = "Сейчас у меня технические трудности с сервером, попробуй ещё раз чуть позже."

    history.append({"role": "assistant", "content": reply_text})
    save_memory(memory)

    return reply_text

# ================= КОМАНДЫ ================= #

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    get_user_state(user_id)
    await message.answer(
        "Привет! Я твой личный ассистент-компаньон 🫶\n"
        "Я запоминаю диалог, храню задачи, заметки и напоминания.\n\n"
        "Команды:\n"
        "• /addtask ТЕКСТ — добавить задачу\n"
        "• /tasks — показать задачи\n"
        "• /cleartasks — очистить задачи\n"
        "• /remember ТЕКСТ — запомнить факт/заметку\n"
        "• /notes — показать заметки\n"
        "• /remind ГГГГ-ММ-ДД ЧЧ:ММ ТЕКСТ — создать напоминание\n"
        "• /reminders — показать будущие напоминания\n\n"
        "Также я понимаю фразы:\n"
        "«добавь задачу …», «покажи мои задачи», «очисти задачи»,\n"
        "«напомни 2 декабря в 15:00…», «напомни через 2 минуты…»,\n"
        "«что там по напоминаниям?», «ты мне что-то должен напомнить?»,\n"
        "«запланировал ли я что-то?»."
    )

# ---- Задачи ---- #

@dp.message(Command("addtask"))
async def cmd_addtask(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Напиши задачу после команды, например:\n/addtask записаться к врачу")
        return

    task_text = parts[1].strip()
    state["tasks"].append(task_text)
    save_memory(memory)
    await message.answer(f"Запомнил задачу:\n• {task_text}")

@dp.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    tasks = state["tasks"]

    if not tasks:
        await message.answer("У тебя пока нет сохранённых задач 🙂")
        return

    text = "Твои задачи:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks))
    await message.answer(text)

@dp.message(Command("cleartasks"))
async def cmd_cleartasks(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    state["tasks"] = []
    save_memory(memory)
    await message.answer("Я удалил все задачи. Можем начать список заново ✨")

# ---- Заметки ---- #

@dp.message(Command("remember"))
async def cmd_remember(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Напиши, что запомнить, например:\n/remember я хочу выучить английский")
        return

    note = parts[1].strip()
    state["notes"].append(note)
    save_memory(memory)
    await message.answer(f"Запомнил это про тебя:\n• {note}")

@dp.message(Command("notes"))
async def cmd_notes(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    notes = state["notes"]

    if not notes:
        await message.answer("У меня пока нет сохранённых заметок про тебя 🙂")
        return

    text = "Вот что я про тебя помню:\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))
    await message.answer(text)

# ================= НАПОМИНАНИЯ ================= #

async def send_reminder(user_id: int, text: str):
    try:
        await bot.send_message(user_id, f"🔔 Напоминание:\n{text}")
    except Exception:
        pass

@dp.message(Command("remind"))
async def cmd_remind(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)

    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "Формат команды:\n"
            "/remind ГГГГ-ММ-ДД ЧЧ:ММ текст напоминания\n\n"
            "Например:\n"
            "/remind 2025-12-02 18:30 позвонить маме"
        )
        return

    date_str, time_str, reminder_text = parts[1], parts[2], parts[3]

    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer(
            "Не понял дату/время 😔\n"
            "Нужен формат: /remind ГГГГ-ММ-ДД ЧЧ:ММ текст\n"
            "Например:\n/remind 2025-12-02 18:30 сходить в зал"
        )
        return

    state["reminders"].append({
        "datetime": dt.isoformat(),
        "text": reminder_text,
    })
    save_memory(memory)

    scheduler.add_job(
        send_reminder,
        "date",
        run_date=dt,
        args=[user_id, reminder_text],
    )

    await message.answer(
        f"Ок, напомню {dt.strftime('%d.%m.%Y в %H:%M')}:\n• {reminder_text}"
    )

@dp.message(Command("reminders"))
async def cmd_reminders(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    reminders = state["reminders"]

    if not reminders:
        await message.answer("У тебя пока нет запланированных напоминаний 🙂")
        return

    now = datetime.now()
    lines = []
    for r in reminders:
        try:
            dt = datetime.fromisoformat(r["datetime"])
        except Exception:
            continue
        if dt < now:
            continue
        lines.append(f"{dt.strftime('%d.%m.%Y %H:%M')} — {r['text']}")

    if not lines:
        await message.answer("У тебя нет будущих напоминаний.")
    else:
        text = "Твои ближайшие напоминания:\n" + "\n".join(lines)
        await message.answer(text)

# ================= ПОМОЩНИКИ: ЗАДАЧИ ================= #

def extract_task_from_text(text: str) -> Optional[str]:
    t = text.lower()
    prefixes = [
        "добавь задачу",
        "запиши задачу",
        "добавь в задачи",
        "добавь в список",
        "запиши в список",
    ]
    for prefix in prefixes:
        if t.startswith(prefix):
            return text[len(prefix):].strip(" :–-")
    return None

def is_show_tasks_intent(text: str) -> bool:
    t = text.lower()
    if "задач" in t and ("покажи" in t or "что мне" in t or "какие" in t):
        return True
    phrases = [
        "покажи мои задачи",
        "покажи задачи",
        "список задач",
        "какие у меня задачи",
        "что мне нужно сделать",
        "что я должен сделать",
    ]
    return any(p in t for p in phrases)

def is_clear_tasks_intent(text: str) -> bool:
    t = text.lower()
    if "задач" in t and ("очисти" in t or "удали" in t or "сбрось" in t):
        return True
    phrases = [
        "очисти задачи",
        "удали задачи",
        "удали все задачи",
        "очисти список задач",
        "сбрось задачи",
    ]
    return any(p in t for p in phrases)

# ================= ПОМОЩНИКИ: ЕСТЕСТВЕННЫЕ НАПОМИНАНИЯ ================= #

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

def parse_natural_reminder(text: str) -> Optional[Tuple[datetime, str]]:
    """
    'напомни мне 2 декабря в 15.00 посмотреть задачи'
    """
    t = text.lower().strip()
    if not t.startswith("напомни"):
        return None

    t = re.sub(r"^напомни( мне)?\s*", "", t, flags=re.IGNORECASE)

    pattern = r"^(\d{1,2})\s+([а-яё]+)\s+в\s+(\d{1,2})[.:](\d{2})\s+(.+)$"
    m = re.match(pattern, t, flags=re.IGNORECASE)
    if not m:
        return None

    day = int(m.group(1))
    month_name = m.group(2)
    hour = int(m.group(3))
    minute = int(m.group(4))
    text_reminder = m.group(5).strip()

    month = MONTHS_RU.get(month_name)
    if not month:
        return None

    year = datetime.now().year
    dt = datetime(year, month, day, hour, minute)

    if dt < datetime.now():
        dt = datetime(year + 1, month, day, hour, minute)

    return dt, text_reminder

def parse_relative_reminder(text: str) -> Optional[Tuple[datetime, str]]:
    """
    'напомни через 2 минуты выпить воды'
    'через 10 минут напомни проверить чайник'
    """
    t = text.lower().strip()

    # варианты начала: "напомни через" или просто "через ..."
    if t.startswith("напомни"):
        t = re.sub(r"^напомни( мне)?\s*", "", t, flags=re.IGNORECASE)

    pattern = r"^через\s+(\d+)\s+(секунд[уы]?|минут[уы]?|час[аов]?)(?:\s+)(.+)$"
    m = re.match(pattern, t)
    if not m:
        return None

    amount = int(m.group(1))
    unit = m.group(2)
    reminder_text = m.group(3).strip()

    now = datetime.now()

    if "секунд" in unit:
        delta = timedelta(seconds=amount)
    elif "минут" in unit:
        delta = timedelta(minutes=amount)
    elif "час" in unit:
        delta = timedelta(hours=amount)
    else:
        return None

    dt = now + delta
    return dt, reminder_text

def is_show_reminders_intent(text: str) -> bool:
    t = text.lower()
    if "напоминан" in t and ("что там" in t or "какие" in t or "есть" in t or "покажи" in t):
        return True
    if "запланировал" in t and ("что-то" in t or "ли я" in t):
        return True
    phrases = [
        "покажи какие есть напоминания",
        "покажи напоминания",
        "какие есть напоминания",
        "какие напоминания у меня есть",
        "какие напоминания у нас есть",
        "что там по напоминаниям",
        "ты мне что-то должен напомнить",
        "ты мне что-то должен был напомнить",
        "запланировал ли я что-то",
        "есть ли у меня напоминания",
        "покажи список напоминаний",
        "покажи мои напоминания",
        "что ты мне напоминаешь",
    ]
    return any(p in t for p in phrases)

def is_how_reminder_works_intent(text: str) -> bool:
    t = text.lower()
    phrases = [
        "как ты напомнишь",
        "как ты мне напомнишь",
        "каким образом ты мне напомнишь",
        "как работает напоминание",
        "как работают напоминания",
        "как ты будешь напоминать",
        "как происходит напоминание",
    ]
    return any(p in t for p in phrases)

# ================= ОБРАБОТКА СООБЩЕНИЙ ================= #

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text

    # 0) объяснение, как работают напоминания
    if is_how_reminder_works_intent(user_text):
        await message.answer(
            "Я запоминаю напоминание и в нужный момент отправляю тебе сообщение прямо сюда, в Telegram 💛\n\n"
            "Я использую встроенный планировщик, так что можешь рассчитывать, "
            "что я напомню вовремя — и о задачах, и о важных мелочах."
        )
        return

    # 1) относительные напоминания: "напомни через 2 минуты ..."
    rel = parse_relative_reminder(user_text)
    if rel is not None:
        dt, text_reminder = rel
        state = get_user_state(user_id)

        state["reminders"].append({
            "datetime": dt.isoformat(),
            "text": text_reminder,
        })
        save_memory(memory)

        delta = dt - datetime.now()
        minutes = delta.seconds // 60
        seconds = delta.seconds % 60

        if minutes > 0:
            when_text = f"через {minutes} мин"
        else:
            when_text = f"через {seconds} сек"

        scheduler.add_job(
            send_reminder,
            "date",
            run_date=dt,
            args=[user_id, text_reminder],
        )

        await message.answer(
            f"Хорошо, напомню {when_text}:\n• {text_reminder}"
        )
        return

    # 2) естественные напоминания по дате: "напомни 2 декабря в 15:00 ..."
    parsed = parse_natural_reminder(user_text)
    if parsed is not None:
        dt, text_reminder = parsed
        state = get_user_state(user_id)

        state["reminders"].append({
            "datetime": dt.isoformat(),
            "text": text_reminder,
        })
        save_memory(memory)

        scheduler.add_job(
            send_reminder,
            "date",
            run_date=dt,
            args=[user_id, text_reminder],
        )

        await message.answer(
            f"Хорошо, напомню {dt.strftime('%d.%m.%Y в %H:%M')}:\n• {text_reminder}"
        )
        return

    # 3) показать напоминания естественной фразой
    if is_show_reminders_intent(user_text):
        await cmd_reminders(message)
        return

    # 4) задачи — добавить
    task_text = extract_task_from_text(user_text)
    if task_text:
        state = get_user_state(user_id)
        state["tasks"].append(task_text)
        save_memory(memory)
        await message.answer(f"Записал задачу:\n• {task_text}")
        return

    # 5) задачи — показать
    if is_show_tasks_intent(user_text):
        await cmd_tasks(message)
        return

    # 6) задачи — очистить
    if is_clear_tasks_intent(user_text):
        await cmd_cleartasks(message)
        return

    # 7) обычный диалог с моделью
    reply = await ask_llm(user_id, user_text)
    await message.answer(reply)

# ================= ВОССТАНОВЛЕНИЕ НАПОМИНАНИЙ ================= #

def restore_reminders():
    now = datetime.now()
    for uid, state in memory.items():
        reminders = state.get("reminders", [])
        for r in reminders:
            try:
                dt = datetime.fromisoformat(r["datetime"])
            except Exception:
                continue
            if dt > now:
                scheduler.add_job(
                    send_reminder,
                    "date",
                    run_date=dt,
                    args=[int(uid), r["text"]],
                )

# ================= ЗАПУСК ================= #

async def main():
    scheduler.start()
    restore_reminders()
    print("Бот запущен. Можно писать ему в Telegram.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

