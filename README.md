# ParserInTelegramBot

Телеграм-бот, который автоматически парсит изображения с сайта Rule34 по заданным тегам и отправляет их в указанный чат.

## 🚀 Возможности

- Получение контента по тегам с Rule34.
- Отправка контента в Telegram-чат.
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
   API_R34 = &api_key=YOUR_RULE34_API_KEY&user_id=YOUR_ID
   GEMINI_API_KEY = YOUR_GEMINI_API_KEY
   GEMINI_MODEL = gemini-2.0-flash
   PROMPT_FOR_TITLE = Преобразуй список тегов в одно красивое и образное предложение на русском языке. Не используй хэштеги, ссылки, технические термины (POV, 3D, CGI, AI, рендер, формат, изображение, иллюстрация, видео, анимация). Упоминай только тех персонажей и вселенную (фандом), которые указаны в тегах, и то, что они делают. Можно добавить лёгкие художественные детали для создания атмосферы (например, настроение, пейзаж, эмоции), но без выдумывания новых событий или героев. Пиши в литературном стиле, как в описании сцены в книге но в одном предложении. Максимум 20-30 слов.
   ```
## 🔑 Получение ключей и токенов

Перед запуском бота необходимо получить токены и API-ключи для корректной работы.

1. TELEGRAM_BOT_TOKEN
- Перейдите в @BotFather в Telegram.
- Создайте нового бота командой /newbot.
- Укажите название и юзернейм для бота.
- Скопируйте выданный токен и вставьте его в .env как TELEGRAM_BOT_TOKEN.

2. TELEGRAM_CHAT_ID_T и TELEGRAM_CHAT_ID_V
- Добавьте созданного бота в ваш Telegram-чат (группу или канал).
- Напишите в чат любое сообщение.
- Перейдите по ссылке:
```bash
https://api.telegram.org/bot<ВАШ_TELEGRAM_BOT_TOKEN>/getUpdates
```
- Найдите поле "chat":{"id":...} в ответе — это ваш chat_id.
- Укажите его в .env:
- TELEGRAM_CHAT_ID_T — для текстовых/изображений.
- TELEGRAM_CHAT_ID_V — для видео (можно использовать один и тот же чат).
* Или можно использовать ботов котрые выдают твой ID как GetMyIDBot

3. API_R34
- Зарегистрируйтесь или авторизуйтес на сайте [Rule34](https://rule34.xxx/index.php?page=account&s=home)
- В [настройках профиля](https://rule34.xxx/index.php?page=account&s=options) получите API Key и User ID.
- Необходимо нажать на галочку Generate New Key? и сохраниться
- Подставьте их в переменную: API_R34 = &api_key=ВАШ_API_KEY&user_id=ВАШ_USER_ID

4. GEMINI_API_KEY
- Перейдите в [Google AI Studio](https://aistudio.google.com/app/apikey)
- Создайте новый проект и сгенерируйте API-ключ.
- Скопируйте его в .env как GEMINI_API_KEY.

## ▶️ Запуск

Запустите бота:

```bash
python main.py
```

Или используйте команду `python main.py` в терминале.
