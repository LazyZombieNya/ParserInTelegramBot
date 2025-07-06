# ParserInTelegramBot

Телеграм-бот, который автоматически парсит изображения с сайта Rule34 по заданным тегам и отправляет их в указанный чат.

## 🚀 Возможности

- Получение изображений по тегам с Rule34.
- Отправка изображений в Telegram-чат.
- Настройка тегов и ссылок через `.env`.

## 📦 Установка

1. Клонируйте репозиторий:

   ```bash
   git clone https://github.com/LazyZombieNya/ParserInTelegramBot.git
   cd ParserInTelegramBot
   ```

2. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

3. Создайте файл `.env` в корне проекта и добавьте в него:

   ```env
   TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID

   TAGS_34=anime,star_wars,female
   WEBSITE_34=https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&tags=
   POST_URL_34=https://rule34.xxx/index.php?page=post&s=view&id=
   ```

## ▶️ Запуск

Запустите бота:

```bash
python main.py
```

Или используйте команду `python main.py` в терминале.
