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
   TELEGRAM_CHAT_ID_T=YOUR_TELEGRAM_CHAT_ID_FOR_ALL
   TELEGRAM_CHAT_ID_V=YOUR_TELEGRAM_CHAT_ID_FOR_VIDEO
   TAGS_34_T = anime,star_wars,female
   TAGS_34_V = video
   UNWANTED_TAGS_34 = +-male+-bara
   WEBSITE_34 = https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&tags=
   POST_URL_34 = https://rule34.xxx/index.php?page=post&s=view&id=
   RATING_POST = score:>=200+
   GEMINI_API_KEY = YOUR_GEMINI_API_KEY
   GEMINI_MODEL = gemini-2.0-flash
   PROMPT_FOR_TITLE = Сформулируй краткое описание поста в 1–2 предложениях на русском языке, без хэштегов, ссылок и технических деталей (POV, 3D, CGI, рендер, формат,изображение, видео и пр.). Оставь только персонажей, вселенную (фандом), обстановку и общую суть действия.

   ```

## ▶️ Запуск

Запустите бота:

```bash
python main.py
```

Или используйте команду `python main.py` в терминале.
