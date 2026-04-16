# Tg_Logist_bot

Проект теперь состоит из двух частей:

1. `bot.py` - Telegram-бот, который показывает пользователю актуальные заявки.
2. `load_server.py` - сервер и веб-приложение для добавления заявок в БД и выдачи их боту по API.

## Что умеет сервер

- открывает веб-страницу для ручного добавления заявок: `http://127.0.0.1:5004/`
- сохраняет заявки в SQLite (`loads.db`)
- отдаёт заявки для бота по API:
  - `GET /loads/latest`
  - `POST /api/loads`
  - `GET /api/loads`

Формат ответа `GET /loads/latest` уже совместим с текущим `bot.py`.

## Запуск

Установить зависимости:

```bash
pip install -r requirements.txt
```

Запустить сервер:

```bash
python load_server.py
```

Запустить бота:

```bash
python bot.py
```

## Переменные окружения

Для бота уже используются:

- `BOT_TOKEN`
- `ADMINS`
- `SERVER_BASE_URL`
- `SERVER_ENDPOINT`
- `SERVER_API_KEY`

Для сервера можно дополнительно указать:

- `LOADS_DB_PATH=loads.db`
- `SERVER_HOST=127.0.0.1`
- `SERVER_PORT=5004`
- `SERVER_API_KEY=...`
- `FLASK_SECRET_KEY=...`

## Пример API-запроса на создание заявки

```bash
curl -X POST http://127.0.0.1:5004/api/loads \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"direction\":\"Ташкент - Москва\",\"cargo\":\"Текстиль, 20 тонн\",\"transport\":\"Тент\",\"date\":\"2026-04-16\",\"extra\":\"Срочная погрузка\"}"
```
