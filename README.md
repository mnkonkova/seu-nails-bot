# lubabot

Telegram-бот для записи на приёмы с зеркалированием в Google Sheets.

## Возможности

**Админы** (`mashakon`, `lyubovseu` — задаются в `.env`):
- Добавление даты с выбором часовых окон (8:00–22:00, пикер с тоглом). На каждую дату создаётся отдельный лист в Google-таблице.
- Просмотр активных (≥ сегодня) дат со счётчиком «свободно/всего».
- Удаление целой даты либо отдельного окна. Удаление чистит и БД, и лист/строку в таблице.
- Освобождение занятого окна — снимает бронь без удаления самого окна; если бронил живой клиент, ему приходит уведомление в TG.
- Запись «внешнего» клиента на свободное окно — для клиентов, которые пришли не через бот. В таблицу пишется переданное админом имя (без TG-ссылки).
- Автоматическая ежедневная чистка прошедших дат в 00:05 MSK (APScheduler).

**Клиенты**:
- Просмотр дат со свободными окнами.
- Запись на окно через подтверждение; при брони в таблицу пишется `@username` с гиперссылкой на TG-профиль (через `textFormat.link`, а не формулу — работает в любой локали).
- Если у клиента нет username — пишется имя из Telegram со ссылкой `tg://user?id=…` (клик открывает профиль в Telegram-клиенте).
- Просмотр и отмена своих записей.
- Подписка на уведомления о новых датах (бот рассылает подписчикам при добавлении админом даты).
- Отзыв одним сообщением — попадает в лист `Feedback`.

## Стек

- Python 3.11, aiogram 3
- SQLAlchemy 2.0 async + SQLite (aiosqlite) — источник правды
- gspread + google-auth — зеркалирование в Google Sheets
- pydantic-settings — конфиг
- APScheduler — ежедневная чистка прошедших дат
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

**Админ:** `/add` (добавить дату с выбором окон), `/dates` (список), `/adminbook` (записать клиента), `/del` (удалить)

Параллельно доступны текстовые кнопки в reply-клавиатуре — меню открывается по `/start`.

## Архитектура

```
app/
├── bot.py, __main__.py        # entrypoint, регистрация роутеров, запуск scheduler
├── config.py                  # env через pydantic-settings
├── smoke.py                   # end-to-end проверка Sheets одним скриптом
├── db/                        # SQLAlchemy: models, session (+ миграции), repos
├── sheets/                    # gspread + retry + async-обёртка + textFormat.link
├── services/
│   ├── booking.py             # оркестратор БД↔Sheets (create/delete/book/unbook/feedback/admin_book_external)
│   ├── notify.py              # броадкаст подписчикам о новых датах
│   └── scheduler.py           # APScheduler: ежесуточная чистка прошедших дат 00:05 MSK
├── handlers/
│   ├── common.py              # /start, /help, /cancel
│   ├── admin/                 # add_date (FSM + пикер окон), view_dates, book_external, delete
│   └── client/                # browse, book, my_bookings, feedback, subscribe
├── keyboards/inline.py        # reply-меню + inline-кнопки + CallbackData
├── middlewares/               # UserCtxMiddleware + AdminFilter
└── utils/                     # dates (MSK), logging
```

Sheets-операции оборачиваются в транзакцию БД: если запись в таблицу падает, откатываем БД. Исключение — создание даты: лист делается первым, при фэйле БД best-effort чистим лист.

Гиперссылки в таблицу ставятся через `userEnteredFormat.textFormat.link` (а не `=HYPERLINK()`) — чтобы не зависеть от локали таблицы: в русской локали формула требует `;` вместо `,`, и всё бы ломалось.

## Данные

- **SQLite**: `./data/lubabot.db` (volume). Таблицы: `users`, `slot_dates`, `slots`, `feedback`. У слотов есть `external_client_name` — если заполнен, значит запись сделана админом за офлайн-клиента.
- **Google Sheets**:
  - Лист на каждую дату, имя = `YYYY-MM-DD`, колонки: `Время | Кто записан | Время записи`.
    - «Кто записан»: `@username` (hyperlink → `t.me/username`), либо «Имя Фамилия» (hyperlink → `tg://user?id=…`), либо имя внешнего клиента без ссылки.
  - Постоянный лист `Feedback`: `Дата | TG | Текст`.

## Тесты

Юнит-тесты на сервисный слой (in-memory SQLite, моки Sheets) + контракт-тесты хендлера на уведомления:

```bash
sudo docker run --rm --network=host -v "$(pwd)":/src -w /src \
  python:3.11-slim \
  bash -c "pip install --quiet --index-url https://pypi.yandex-team.ru/simple/ -e '.[dev]' && python -m pytest tests/ -v"
```

Покрывают: возврат списка `BookingNotification` из `delete_date`/`delete_slot`/`admin_clear_slot`, фильтрацию внешних клиентов из нотификаций, пере-бронирование после `clear`, и что `_notify()` не роняет админский флоу при сбое `bot.send_message`.

## Смок-тест

Прогоняет create_date → book → unbook → rebook (без username) → submit_feedback → delete_date через реальный Google Sheets API, паузя на Enter между шагами для визуальной проверки.

```bash
sudo docker run --rm -it --env-file .env -e TZ=Europe/Moscow \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/credentials/gsheets.json:/app/credentials/gsheets.json:ro" \
  --network host \
  lubabot:latest python -m app.smoke
```

Использует вымышленные `tg_id`, чтобы не конфликтовать с реальными пользователями.

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

**Миграции.** Для простых случаев (добавить nullable-колонку) в `app/db/session.py::_apply_adhoc_migrations` есть легковесный helper: на старте он проверяет колонки через `inspect()` и делает нужные `ALTER TABLE ADD COLUMN`. Идемпотентно, на свежей БД — no-op.

Для более сложных изменений (DROP/RENAME/type change, NOT NULL без дефолта) — либо допишите свою ветку в `_apply_adhoc_migrations`, либо переезжайте на Alembic.

## Бэкап

```bash
sqlite3 data/lubabot.db ".backup 'data/lubabot-$(date +%F).db'"
```

Google-таблица уже является вторичной копией бронирований.
