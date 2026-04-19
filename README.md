# lubabot

Telegram-бот для записи на приёмы с зеркалированием в Google Sheets.

## Возможности

**Админы** (`mashakon`, `lyubovseu` — задаются в `.env`):
- Добавление даты с выбором часовых окон (8:00–22:00, пошагово). На каждую дату создаётся отдельный лист в Google-таблице.
- Просмотр активных (≥ сегодня) дат со счётчиком «свободно/всего».
- Удаление целой даты либо отдельного окна. Удаление чистит и БД, и лист/строку в таблице.

**Клиенты**:
- Просмотр дат со свободными окнами.
- Запись на окно через подтверждение; при брони в таблицу пишется кликабельная ссылка на TG-профиль.
- Просмотр и отмена своих записей.
- Подписка на уведомления о новых датах.
- Отзыв одним сообщением — попадает в лист `Feedback`.

Прошедшие даты планируется автоматически удалять раз в сутки (планировщик ещё не подключён).

## Стек

- Python 3.11, aiogram 3
- SQLAlchemy 2.0 async + SQLite (aiosqlite) — источник правды
- gspread + google-auth — зеркалирование в Google Sheets
- pydantic-settings — конфиг
- APScheduler — (placeholder) периодические задачи
- tenacity — ретраи для Sheets API
- Docker — деплой

## Требования

- Docker (или docker compose)
- Telegram-бот: токен от [@BotFather](https://t.me/BotFather)
- Google Cloud:
  - Создать проект, включить **Google Sheets API**
  - Создать сервисный аккаунт, скачать JSON-ключ
  - Создать Google-таблицу; расшарить её на email сервисного аккаунта с правом «Редактор»
  - ID таблицы — часть URL между `/d/` и `/edit`

## Быстрый старт (Docker)

```bash
git clone <this-repo> lubabot && cd lubabot

cp .env.example .env
# отредактировать .env: BOT_TOKEN, SHEETS_SPREADSHEET_ID, ADMIN_USERNAMES

mkdir -p credentials data
cp /path/to/gsheets-key.json credentials/gsheets.json

# собрать и запустить
UID=$(id -u) GID=$(id -g) docker compose up -d --build
docker compose logs -f bot
```

### Без docker compose (только `docker`)

Если на хосте нет compose-плагина:

```bash
docker build --network=host \
  --build-arg UID=$(id -u) --build-arg GID=$(id -g) \
  -t lubabot:latest .

docker run -d --name lubabot --restart unless-stopped \
  --env-file .env -e TZ=Europe/Moscow \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/credentials/gsheets.json:/app/credentials/gsheets.json:ro" \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  lubabot:latest

docker logs -f lubabot
```

### Корпоративный pip-mirror (опционально)

Если твой PyPI недоступен напрямую, прокинь мирор:

```bash
docker build --build-arg PIP_INDEX_URL=https://pypi.example.com/simple/ ...
```

## Переменные окружения

| Переменная | Обязательная | Пример | Описание |
|------------|:-:|---|---|
| `BOT_TOKEN` | ✓ | `12345:abcd…` | Токен Telegram-бота |
| `ADMIN_USERNAMES` | ✓ | `mashakon,lyubovseu` | TG-юзернеймы админов через запятую, без `@` |
| `SHEETS_SPREADSHEET_ID` | ✓ | `1AbCd…xyz` | ID Google-таблицы |
| `SHEETS_CREDENTIALS_PATH` |   | `/app/credentials/gsheets.json` | Путь к JSON-ключу в контейнере |
| `DB_PATH` |   | `/app/data/lubabot.db` | Путь к SQLite |
| `LOG_LEVEL` |   | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

## Команды в боте

**Общие:** `/start`, `/help`, `/cancel`

**Клиент:** `/browse`, `/my`, `/feedback`, `/subscribe`, `/unsubscribe`

**Админ:** `/add` (добавить дату с выбором окон), `/dates` (список), `/del` (удалить)

Параллельно доступны текстовые кнопки в reply-клавиатуре — меню открывается по `/start`.

## Архитектура

```
app/
├── bot.py, __main__.py        # entrypoint, регистрация роутеров
├── config.py                  # env через pydantic-settings
├── db/                        # SQLAlchemy: models, session, repos
├── sheets/                    # gspread + retry + async-обёртка
├── services/
│   ├── booking.py             # оркестратор БД↔Sheets (create/delete/book/unbook/feedback)
│   └── notify.py              # броадкаст подписчикам о новых датах
├── handlers/
│   ├── common.py              # /start, /help, /cancel
│   ├── admin/                 # add_date (FSM + пикер окон), view_dates, delete
│   └── client/                # browse, book, my_bookings, feedback, subscribe
├── keyboards/inline.py        # reply-меню + inline-кнопки + CallbackData
├── middlewares/               # UserCtxMiddleware + AdminFilter
└── utils/                     # dates (MSK), logging
```

Sheets-операции оборачиваются в транзакцию БД: если запись в таблицу падает, откатываем БД. Исключение — создание даты: лист делается первым, при фэйле БД best-effort чистим лист.

## Данные

- **SQLite**: `./data/lubabot.db` (volume)
- **Google Sheets**:
  - Лист на каждую дату, имя = `YYYY-MM-DD`, колонки: `Время | Кто записан | Время записи`
  - Постоянный лист `Feedback`: `Дата | TG | Текст`

## Типовые проблемы

- **Бот пишет «Дата в прошлом»** — часовой пояс в контейнере должен быть `Europe/Moscow` (выставляется через `TZ` env и `tzdata` образа).
- **`json.decoder.JSONDecodeError` при старте** — формат `ADMIN_USERNAMES`: строка через запятую, без скобок и кавычек (`mashakon,lyubovseu`).
- **Ошибки Google API** — проверь, что таблица расшарена на email сервисного аккаунта (`client_email` из JSON) с правами редактора.
- **UID-конфликт на volume** — собирай с `--build-arg UID=$(id -u) --build-arg GID=$(id -g)`, иначе контейнер под UID 1000 не сможет писать в `./data`, созданный твоим пользователем.

## Обновление

```bash
git pull
UID=$(id -u) GID=$(id -g) docker compose up -d --build
# или: docker build ... && docker rm -f lubabot && docker run ...
```

При изменении схемы БД на уже прогретой инсталляции SQL миграций пока нет — удаляй `data/lubabot.db` или делай `ALTER TABLE` руками (в момент первой альтерации стоит подключить Alembic).

## Бэкап

```bash
sqlite3 data/lubabot.db ".backup 'data/lubabot-$(date +%F).db'"
```

Google-таблица уже является вторичной копией бронирований.
