from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def user_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Актуальные заявки", callback_data="loads")],
        [InlineKeyboardButton(text="📌 Статус доступа", callback_data="status")],
        [InlineKeyboardButton(text="📞 Изменить номер телефона", callback_data="change_phone")],
    ])

def phone_request_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📲 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def admin_decision_kb(req_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"approve:{req_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{req_id}"),
        ]
    ])

def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Показать pending", callback_data="admin:pending")]
    ])
