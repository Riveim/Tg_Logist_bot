import os
import re
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

from db import DB
from keyboards import user_menu, phone_request_kb, admin_decision_kb, admin_panel_kb
from server_client import ServerClient

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMINS = {int(x.strip()) for x in os.getenv("ADMINS", "").split(",") if x.strip().isdigit()}

WEEK_PRICE = int(os.getenv("WEEK_PRICE_UZS", "20000"))
ACCESS_DAYS = int(os.getenv("ACCESS_DAYS", "7"))

# Уведомления админу
ADMIN_NOTIFY = os.getenv("ADMIN_NOTIFY", "1") == "1"           # важные события
ADMIN_NOTIFY_LOADS = os.getenv("ADMIN_NOTIFY_LOADS", "0") == "1"  # "🚚 открыл заявки" (спамно)

db = DB("bot.db")
server = ServerClient()

PHONE_RE = re.compile(r"^\+998\d{9}$")  # +998901234567


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


def normalize_phone(s: str) -> str | None:
    s = s.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if s.startswith("998") and not s.startswith("+998"):
        s = "+" + s
    if PHONE_RE.fullmatch(s):
        return s
    return None


async def admin_notify(bot: Bot, text: str, *, important: bool = True):
    """
    Шлёт уведомления админу(ам) в личку.
    important=True  -> всегда, если ADMIN_NOTIFY=1
    important=False -> только если ADMIN_NOTIFY_LOADS=1
    """
    if not ADMIN_NOTIFY:
        return
    if (not important) and (not ADMIN_NOTIFY_LOADS):
        return

    for admin_id in ADMINS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            # чтобы бот не падал из-за проблем с отправкой админу
            pass


async def notify_admins_new_request(bot: Bot, tg_id: int, phone: str, req_id: int):
    text = (
        "🧾 *Новый запрос доступа*\n"
        f"TG ID: `{tg_id}`\n"
        f"Телефон: `{phone}`\n"
        f"Тариф: *{WEEK_PRICE}* сум / *{ACCESS_DAYS}* дней\n"
        f"Request ID: `{req_id}`\n\n"
        "Действия:\n"
        "1) Выставь счёт в Click Business на этот номер\n"
        "2) После оплаты нажми ✅ Подтвердить оплату"
    )
    for admin_id in ADMINS:
        try:
            await bot.send_message(admin_id, text, reply_markup=admin_decision_kb(req_id))
        except Exception:
            pass


def format_loads(data: dict) -> str:
    # Ожидаем JSON формата: {"loads":[{...},{...}]}
    if isinstance(data, dict) and "loads" in data and isinstance(data["loads"], list):
        loads = data["loads"][:20]
        if not loads:
            return "Пока нет актуальных заявок."
        out = ["🚚 *Актуальные заявки:*"]
        for i, item in enumerate(loads, 1):
            frm = item.get("from", "—")
            to = item.get("to", "—")
            cargo = item.get("cargo", "")
            price = item.get("price", "")
            contact = item.get("phone", "") or item.get("contact", "")
            out.append(f"\n{i}) *{frm} → {to}*")
            if cargo:
                out.append(f"📦 {cargo}")
            if price:
                out.append(f"💰 {price}")
            if contact:
                out.append(f"☎️ {contact}")
        return "\n".join(out)

    return f"Ответ сервера:\n`{str(data)[:3500]}`"


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty")

    bot = Bot(BOT_TOKEN, parse_mode="Markdown")
    dp = Dispatcher()

    # кто сейчас в режиме ввода телефона
    waiting_phone: set[int] = set()

    async def ask_phone(chat_id: int):
        await bot.send_message(
            chat_id,
            "Введи номер телефона в формате `+998901234567` или нажми кнопку «📲 Отправить номер».",
            reply_markup=phone_request_kb()
        )

    @dp.message(CommandStart())
    async def start(m: Message):
        tg_id = m.from_user.id
        db.ensure_user(tg_id)

        await admin_notify(bot, f"👤 /start от `{tg_id}`", important=True)

        # админ-панель
        if is_admin(tg_id):
            await m.answer(
                "Админ-меню: нажми кнопку или используй /pending",
                reply_markup=admin_panel_kb()
            )

        if db.has_access(tg_id):
            until = db.get_access_until(tg_id)
            await m.answer(
                f"✅ Доступ активен до `{until}`.\nНажми «🚚 Актуальные заявки».",
                reply_markup=user_menu()
            )
            return

        phone = db.get_phone(tg_id)
        if not phone:
            waiting_phone.add(tg_id)
            await m.answer(
                f"Для доступа нужен номер телефона.\n"
                f"Тариф: *{WEEK_PRICE}* сум / *{ACCESS_DAYS}* дней.\n",
                reply_markup=user_menu()
            )
            await ask_phone(m.chat.id)
            return

        # телефон есть, но доступа нет
        req_id = db.create_access_request(tg_id, phone)
        await m.answer(
            f"Номер `{phone}` сохранён.\n"
            f"Я выставлю счёт на этот номер. После оплаты я подтвержу и доступ откроется.\n"
            f"ID заявки: `{req_id}`",
            reply_markup=user_menu()
        )

        await notify_admins_new_request(bot, tg_id, phone, req_id)
        await admin_notify(bot, f"🧾 Pending-запрос `{req_id}` от `{tg_id}` (`{phone}`)", important=True)

    @dp.callback_query(F.data == "change_phone")
    async def change_phone(c: CallbackQuery):
        await c.answer()
        waiting_phone.add(c.from_user.id)
        await ask_phone(c.message.chat.id)

    @dp.message(F.contact)
    async def got_contact(m: Message):
        tg_id = m.from_user.id
        phone_raw = m.contact.phone_number

        # Telegram может прислать без "+"
        if phone_raw.startswith("998") and not phone_raw.startswith("+998"):
            phone_raw = "+" + phone_raw

        phone = normalize_phone(phone_raw)
        if not phone:
            await m.answer("Не смог распознать номер. Пришли в формате `+998901234567`.")
            return

        db.set_phone(tg_id, phone)
        waiting_phone.discard(tg_id)

        req_id = db.create_access_request(tg_id, phone)
        await m.answer(
            f"✅ Номер сохранён: `{phone}`\n"
            f"Я выставлю счёт на этот номер. После оплаты подтвержу и доступ откроется.\n"
            f"ID заявки: `{req_id}`",
            reply_markup=user_menu()
        )

        await admin_notify(bot, f"📞 Номер получен: `{phone}` от `{tg_id}`", important=True)
        await notify_admins_new_request(bot, tg_id, phone, req_id)

    @dp.message(F.text)
    async def got_text(m: Message):
        tg_id = m.from_user.id
        if m.text.startswith("/"):
            return

        if tg_id not in waiting_phone:
            return

        phone = normalize_phone(m.text)
        if not phone:
            await m.answer("Неверный формат. Пример: `+998901234567`")
            return

        db.set_phone(tg_id, phone)
        waiting_phone.discard(tg_id)

        req_id = db.create_access_request(tg_id, phone)
        await m.answer(
            f"✅ Номер сохранён: `{phone}`\n"
            f"Я выставлю счёт на этот номер. После оплаты подтвержу и доступ откроется.\n"
            f"ID заявки: `{req_id}`",
            reply_markup=user_menu()
        )

        await admin_notify(bot, f"📞 Номер получен: `{phone}` от `{tg_id}`", important=True)
        await notify_admins_new_request(bot, tg_id, phone, req_id)

    @dp.callback_query(F.data == "status")
    async def status(c: CallbackQuery):
        await c.answer()
        tg_id = c.from_user.id
        until = db.get_access_until(tg_id)

        if db.has_access(tg_id):
            await bot.send_message(
                c.message.chat.id,
                f"✅ Доступ активен до `{until}`",
                reply_markup=user_menu()
            )
            return

        phone = db.get_phone(tg_id)
        if not phone:
            waiting_phone.add(tg_id)
            await bot.send_message(
                c.message.chat.id,
                "⛔️ Доступа нет. Сначала укажи номер.",
                reply_markup=user_menu()
            )
            await ask_phone(c.message.chat.id)
            return

        await bot.send_message(
            c.message.chat.id,
            f"⛔️ Доступа нет.\nНомер `{phone}` есть. После оплаты я подтвержу и открою доступ.",
            reply_markup=user_menu()
        )

    @dp.callback_query(F.data == "loads")
    async def loads(c: CallbackQuery):
        await c.answer()
        tg_id = c.from_user.id

        if not db.has_access(tg_id):
            phone = db.get_phone(tg_id)
            if not phone:
                waiting_phone.add(tg_id)
                await bot.send_message(
                    c.message.chat.id,
                    "⛔️ Доступ закрыт. Укажи номер телефона.",
                    reply_markup=user_menu()
                )
                await ask_phone(c.message.chat.id)
            else:
                await bot.send_message(
                    c.message.chat.id,
                    f"⛔️ Доступ закрыт. Счёт будет выставлен на `{phone}`. После оплаты открою доступ.",
                    reply_markup=user_menu()
                )
            return

        resp = await server.get_loads(tg_id)
        if not resp.get("ok"):
            await bot.send_message(
                c.message.chat.id,
                f"⚠️ Сервер недоступен.\nДетали: `{resp.get('status','')}` `{resp.get('error','')}`",
                reply_markup=user_menu()
            )
            return

        text = format_loads(resp.get("data", {}))
        await bot.send_message(c.message.chat.id, text, reply_markup=user_menu())

        # Неважное уведомление (включается флагом ADMIN_NOTIFY_LOADS=1)
        await admin_notify(bot, f"🚚 Открыл заявки: `{tg_id}`", important=False)

    # ====== АДМИН-ЧАСТЬ ======

    @dp.message(F.text == "/pending")
    async def pending_cmd(m: Message):
        if not is_admin(m.from_user.id):
            return
        pending = db.list_pending(limit=20)
        if not pending:
            await m.answer("Pending-заявок нет.")
            return
        for r in pending:
            await m.answer(
                f"🕒 *PENDING*\n"
                f"Request ID: `{r['id']}`\n"
                f"TG ID: `{r['tg_id']}`\n"
                f"Phone: `{r['phone']}`",
                reply_markup=admin_decision_kb(int(r["id"]))
            )

    @dp.callback_query(F.data == "admin:pending")
    async def pending_btn(c: CallbackQuery):
        if not is_admin(c.from_user.id):
            await c.answer("Нет доступа", show_alert=True)
            return
        await c.answer()
        pending = db.list_pending(limit=20)
        if not pending:
            await bot.send_message(c.message.chat.id, "Pending-заявок нет.")
            return
        for r in pending:
            await bot.send_message(
                c.message.chat.id,
                f"🕒 *PENDING*\n"
                f"Request ID: `{r['id']}`\n"
                f"TG ID: `{r['tg_id']}`\n"
                f"Phone: `{r['phone']}`",
                reply_markup=admin_decision_kb(int(r["id"]))
            )

    @dp.callback_query(F.data.startswith("approve:"))
    async def approve(c: CallbackQuery):
        if not is_admin(c.from_user.id):
            await c.answer("Нет доступа", show_alert=True)
            return

        req_id = int(c.data.split(":")[1])
        row = db.get_request(req_id)
        if not row:
            await c.answer("Не найдено", show_alert=True)
            return
        if row["status"] != "pending":
            await c.answer("Уже решено", show_alert=True)
            return

        db.approve_request(req_id, c.from_user.id)
        until = db.grant_access_days(int(row["tg_id"]), ACCESS_DAYS)

        await c.message.edit_text(
            c.message.text + f"\n\n✅ *APPROVED* до `{until}`",
            reply_markup=None
        )
        await c.answer("Подтверждено")

        await bot.send_message(
            int(row["tg_id"]),
            f"✅ Оплата подтверждена. Доступ открыт до `{until}`.\nНажми «🚚 Актуальные заявки».",
            reply_markup=user_menu()
        )

        await admin_notify(bot, f"✅ APPROVED `{row['tg_id']}` до `{until}` (req `{req_id}`)", important=True)

    @dp.callback_query(F.data.startswith("reject:"))
    async def reject(c: CallbackQuery):
        if not is_admin(c.from_user.id):
            await c.answer("Нет доступа", show_alert=True)
            return

        req_id = int(c.data.split(":")[1])
        row = db.get_request(req_id)
        if not row:
            await c.answer("Не найдено", show_alert=True)
            return
        if row["status"] != "pending":
            await c.answer("Уже решено", show_alert=True)
            return

        db.reject_request(req_id, c.from_user.id)
        await c.message.edit_text(c.message.text + "\n\n❌ *REJECTED*", reply_markup=None)
        await c.answer("Отклонено")

        await bot.send_message(
            int(row["tg_id"]),
            "❌ Оплата не подтверждена. Если нужно — отправь номер снова через /start.",
            reply_markup=user_menu()
        )

        await admin_notify(bot, f"❌ REJECTED `{row['tg_id']}` (req `{req_id}`)", important=True)

    logging.info("Bot started. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
