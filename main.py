import asyncio
import html
import os
import pickle
from collections import deque, defaultdict

import aiofiles
import aiohttp
import httpx
from dotenv import load_dotenv
from google import genai
from telegram import Bot, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, ApplicationBuilder, ContextTypes, AIORateLimiter
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError, RetryAfter

from media_processor import download_media, get_file_extension, clear_data_folder

load_dotenv()  # Загружаем переменные из .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID_T = os.getenv("TELEGRAM_CHAT_ID_T")
TELEGRAM_CHAT_ID_V = os.getenv("TELEGRAM_CHAT_ID_V")
TAGS_34_T = os.getenv("TAGS_34_T", "").split(",")
TAGS_34_V = os.getenv("TAGS_34_V", "").split(",")
UNWANTED_TAGS_34 =os.getenv("UNWANTED_TAGS_34")  # Нежелательные теги, посты с этим тегом будут пропущены
WEBSITE_34 = os.getenv("WEBSITE_34")
POST_URL_34 = os.getenv("POST_URL_34")
API_R34 = os.getenv("API_R34")
RATING_POST = os.getenv("RATING_POST")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL")
GROQ_URL = os.getenv("GROQ_URL")
PROMPT_FOR_TITLE = os.getenv("PROMPT_FOR_TITLE")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

# Списки
LIMIT = 40 #Лимит прогрузки постов по одному тегу
SAVE_FILE = "sent_posts.pkl" # Файл данными об отправленных постах
MAX_POSTS_SAVE = 150 #Количество постов для сохранения в отправленных
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Папка, где лежит main.py

# Ограничения Telegram
LIMIT_CAPTION = 400 #1024 # Лимит символов описания поста телеграмм
LIMIT_TEXT_MSG = 4096  # Лимит символов для одного сообщения телеграмм
MAX_MEDIA_PER_GROUP = 10  # Лимит Telegram на медиа-группу

posts = []  # Не отправленные посты
sent_posts = defaultdict(lambda: deque(maxlen=MAX_POSTS_SAVE))  # ID отправленных постов (отдельно для каждого сайта) с авто удалением старых записей
send_posts_lock = asyncio.Lock()
recorded_sent_posts = False # Флаг сохраненных постов

# Инициализация Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Устанавливаем тайм-ауты (убираем ошибку timeout)
request = HTTPXRequest(connect_timeout=60, read_timeout=60)
# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, request=request)  # Увеличенный таймаут

#Загрузка отправленных постов sent_posts из файла SAVE_FILE
async def load_sent_posts(app: Application):
    global sent_posts
    try:
        async with aiofiles.open(SAVE_FILE, "rb") as file:
            content = await file.read()  # Асинхронно читаем файл
            if content:
                loaded_data = pickle.loads(content)  # Десериализуем
                # Преобразуем обратно в defaultdict с deque
                sent_posts = defaultdict(lambda: deque(maxlen=MAX_POSTS_SAVE),
                                         {key: deque(value, maxlen=MAX_POSTS_SAVE) for key, value in loaded_data.items()})
                print("Sent posts data successfully loaded!")
    except FileNotFoundError:
        print("File with saved posts not found, create a new one.")
    except Exception as e:
        print(f"Error loading: {e}")

#Сохранение отправленных постов sent_posts в файл SAVE_FILE
async def save_sent_posts(app: Application):
    #print("Saving data before exiting...")

    # Преобразуем defaultdict в обычный dict, иначе pickle не сможет его сохранить
    normal_dict = {key: list(value) for key, value in sent_posts.items()}
    try:
        async with aiofiles.open(SAVE_FILE, "wb") as file:
            await file.write(pickle.dumps(normal_dict))
        #print("Data saved successfully!")
    except Exception as e:
        print(f"Error while saving: {e}")


# Функция добавления нового поста (с проверкой дубликатов)
async def save_post(post_id, post_url, title, file_url,tag):
    if post_id in sent_posts[tag] or any(post["post_id"] == post_id for post in posts):
        #print(f"Пост {post_id} уже есть в базе. Пропускаем.")
        return
    # Фильтруем нежелательные расширения сразу
    ext = get_file_extension(file_url)
    if ext not in ('jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'mp4', 'avi', 'mov', 'mkv', 'webm', 'gif'):
        print(f"Unsupported file skipped: {file_url}")
        return

    posts.append({
        "post_id": post_id,
        "post_url": post_url,
        "title": html.escape(title),
        "file_url": file_url,
        "tag": tag,
        "send": "not"
    })
    #print(f"Добавлен пост {post_id}")

# Список ошибок при которых будет производиться попытка повторной отправки
def is_retryable_error(e):
    if isinstance(e, (TimedOut, NetworkError, RetryAfter)):
        return True
    text = str(e).lower()

    retry_texts = [
        "timed out",
        "timeout",
        "networkerror",
        "connecterror",
        "all connection attempts failed",
        "cannot connect to host",
        "getaddrinfo failed",
        "connection reset",
        "server disconnected",
        "retry after",
        "flood control",
        "bad gateway",
        "gateway timeout",
        "webpage_media_empty",
        "webpage_curl_failed",
    ]

    return any(t in text for t in retry_texts)

# Функция отправки постов в Телеграм
async def send_posts(app: Application):
    global posts, recorded_sent_posts

    if not posts:
        #print("Нет новых постов для отправки.")
        await clear_data_folder() #Если все посты отправлены, то скачанные можно удалять
        if recorded_sent_posts:
            await save_sent_posts(app)
            recorded_sent_posts = False

        return

    recorded_sent_posts = True
    for post in posts[:]:  # Копия списка, чтобы можно было изменять оригинал
        title_post = await generate_description_from_tags(post["title"])
        if not title_post.strip():  # если пусто или только пробелы
            title_post = post["title"]
        caption_full = f'<a href="{post["post_url"]}">Пост {post["post_id"]}</a> : {title_post}'  # Эта будет ссылкой на пост
        caption_post = caption_full[:LIMIT_CAPTION] + "..." if len(caption_full) > LIMIT_CAPTION else caption_full #Обрезаем длину Caption если доходит до лимита
        ext_file = get_file_extension(post['file_url'])
        TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID_T if post["tag"] in TAGS_34_T else TELEGRAM_CHAT_ID_V

        media_group = []
        animations = []
        local_files = []  # Список для хранения путей к файлам
        open_file_handles = []  # Список для открытых файловых объектов (чтобы потом закрыть)

        # Если статус err, сразу качаем файл
        if post["send"] == "err":
            local_files = await download_media(post["file_url"])
            if not local_files:
                post["send"] = "close"

        if post["send"] != "close":
            # Если файлы были скачаны, перебираем их
            if local_files:
                # Вычисляем индекс первого файла в ПОСЛЕДНЕМ чанке (группе)
                last_chunk_start_idx = ((len(local_files) - 1) // MAX_MEDIA_PER_GROUP) * MAX_MEDIA_PER_GROUP
                for i, path in enumerate(local_files):
                    media_source = open(path, 'rb')
                    open_file_handles.append(media_source)

                    # Подпись добавляем ТОЛЬКО к первому элементу последнего альбома
                    current_caption = caption_post if i == last_chunk_start_idx else ""

                    if ext_file in ("jpeg", "jpg", "png", "webp"):
                        media_group.append(
                            InputMediaPhoto(media=media_source, caption=current_caption, parse_mode="HTML"))
                    elif ext_file == "mp4":
                        media_group.append(
                            InputMediaVideo(media=media_source, caption=current_caption, parse_mode="HTML"))
                    elif ext_file == "gif":
                        media_group.append(
                            InputMediaVideo(media=media_source, caption=current_caption, parse_mode="HTML"))
            else:
                # Если файл не скачивался, отправляем по URL
                if ext_file in ("jpeg", "jpg", "png", "webp"):
                    media_group.append(InputMediaPhoto(media=post["file_url"], caption=caption_post, parse_mode="HTML"))
                elif ext_file == "mp4":
                    media_group.append(InputMediaVideo(media=post["file_url"], caption=caption_post, parse_mode="HTML"))
                elif ext_file == "gif":
                    animations.append(post["file_url"])
                else:
                    post["send"] = "close"

        # Отправка медиагруппы с обходом лимита в 10 файлов
        if media_group and post["send"] != "close":
            try:
                chunk_size = MAX_MEDIA_PER_GROUP

                # Дробим media_group на списки по 10 элементов
                for i in range(0, len(media_group), chunk_size):
                    chunk = media_group[i:i + chunk_size]

                    # Отправляем текущий кусок альбома
                    await bot.send_media_group(chat_id=TELEGRAM_CHAT_ID, media=chunk)

                    # Если это не последний кусок, делаем паузу, чтобы не словить Flood Control
                    if i + chunk_size < len(media_group):
                        await asyncio.sleep(3)

                post["send"] = "yes"
            except Exception as e:
                status = "идет на повторную загрузку" if is_retryable_error(e) else "будет пропущен"
                print(
                    f"[ПОСТ {post['post_id']} | {post['tag']}] Ошибка отправки группы: {type(e).__name__} ({e}). Статус: {status}")

                if is_retryable_error(e):
                    post["send"] = "err"
                else:
                    post["send"] = "close"

        # Отправка анимаций по URL
        if animations and post["send"] != "close":
            for animation in animations:
                try:
                    await bot.send_animation(chat_id=TELEGRAM_CHAT_ID, animation=animation, caption=caption_post,
                                             parse_mode="HTML")
                    post["send"] = "yes"
                except Exception as e:
                    print(f'Error sending GIF {post["post_id"]}: {repr(e)}')
                    # Если ошибка из списка повторений, сразу помечаем как 'err', чтобы на следующем круге попробовать повторно скачать
                    if is_retryable_error(e):
                        post["send"] = "err"
                    else:
                        post["send"] = "close"

        # Закрываем все локальные файлы, если открывали
        for handle in open_file_handles:
            handle.close()

            # Обработка статусов
        if post["send"] in {"yes", "close"}:
            sent_posts[post["tag"]].append(post["post_id"])
            posts.remove(post)
            if post["send"] == "close":
                print(f"Dont sending post: {post["post_id"]}")
                ext = get_file_extension(post["file_url"]).lower()
                img_caption = "🖼 Файл изображения" if ext in {"jpg", "jpeg", "png", "gif", "bmp",
                                                              "webp"} else "📺 Видео файл"
                caption_dont_send = f'<a href="{post["file_url"]}">{img_caption} не загрузился, вот ссылка</a> \n\n {caption_post}'
                try:
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=caption_dont_send, parse_mode="HTML")
                except Exception as e:
                    print(f"Error sending text message: {e}")

        await asyncio.sleep(5)  # Задержка для Telegram


async def generate_description_from_tags(tags: str) -> str:
    prompt = f"""Here is a list of tags: {tags}.
    {PROMPT_FOR_TITLE}"""

    # 1. Попытка через Gemini
    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=GEMINI_MODEL,
            contents=prompt,
        )

        if response and getattr(response, "text", None):
            return response.text.strip()

        raise RuntimeError("Gemini вернул пустой ответ")

    except Exception as gemini_error:
        #print(f"Gemini error: {gemini_error}")
        pass  # Ошибка произойдет, но бот промолчит и пойдет дальше

    # 2. Fallback на GROQ
    try:
        return await generate_with_groq(prompt)
    except Exception as groq_error:
        print(f"GROQ error: {groq_error}")
        return ""

async def generate_with_groq(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        #"max_tokens": 40,  # примерно 20–25 слов на русском, обрезает предложение
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GROQ_URL, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

"""Асинхронный запрос к сайту."""
async def fetch_html(url):
    try:
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(
                headers=HEADERS,
                timeout=timeout
        ) as session:

            async with session.get(url) as response:

                if response.status == 200:
                    return await response.json()

                print(f"HTTP {response.status}: {url}")
                return None

    except aiohttp.ClientConnectorError as e:
        print(f"DNS/Connection error: {e}")
        return None

    except asyncio.TimeoutError:
        print(f"Timeout: {url}")
        return None

    except Exception as e:
        print(f"fetch_html error: {e}")
        return None

# Основной цикл для проверки новых постов T
async def monitor_website_34_T(app: Application):
    post_id = None
    try:
        viewed_tags = UNWANTED_TAGS_34
        for tag in TAGS_34_T:
            html = await fetch_html(f"{WEBSITE_34}{RATING_POST}{tag}{viewed_tags}&limit={LIMIT}&json=1{API_R34}")
            viewed_tags =  f"{viewed_tags}+-{tag}"

            if not html or not isinstance(html, list):
                print("No posts received or wrong response format, skipping iteration.")
                continue  # Пропускаем обработку если нет ничего

            for post in html:
                post_id = post["id"]
                if post_id not in sent_posts[tag]:
                    file_url = post["file_url"]
                    post_url = f"{POST_URL_34}{post_id}"
                    title = post["tags"]
                    await save_post(post_id, post_url, title, file_url, tag)
    except Exception as e:
        print(f"Error in post {post_id}: {e}")


# Основной цикл для проверки новых постов V
async def monitor_website_34_V(app: Application):
    post_id = None
    try:
        viewed_tags = UNWANTED_TAGS_34
        for tag in TAGS_34_V:
            html = await fetch_html(f"{WEBSITE_34}{RATING_POST}{tag}{viewed_tags}&limit={LIMIT}&json=1{API_R34}")
            viewed_tags =  f"{viewed_tags}+-{tag}"

            if not html or not isinstance(html, list):
                print("No posts received or wrong response format, skipping iteration.")
                continue  # Пропускаем обработку если нет ничего

            for post in html:
                post_id = post["id"]
                if post_id not in sent_posts[tag]:
                    file_url = post["file_url"]
                    post_url = f"{POST_URL_34}{post_id}"
                    title = post["tags"]
                    await save_post(post_id, post_url, title, file_url, tag)
    except Exception as e:
        print(f"Error in post {post_id}: {e}")

async def monitor_website(context: ContextTypes.DEFAULT_TYPE):
    try:
        await monitor_website_34_T(context.application)
        await monitor_website_34_V(context.application)
        if send_posts_lock.locked():
            print("send_posts already running, skip")
            return

        async with send_posts_lock:
            await send_posts(context.application)
        # await asyncio.sleep(60)  # Ждём 60 секунд перед следующим запросом
    except Exception as e:
        print(f"Error in monitor_website: {e}")



# Запуск программы
if __name__ == "__main__":
    #asyncio.run(main())  # Запуск главной асинхронной функции
    # 1. Настраиваем RateLimiter (Решает проблему Flood Control)
    rate_limiter = AIORateLimiter(
        overall_max_rate=30,  # Не более 30 сообщений в секунду (общий лимит)
        overall_time_period=1,
        group_time_period=60,  # Групповые лимиты
        max_retries=5  # Сколько раз повторять при ошибке сети
    )

    # 2. Создаем приложение
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .rate_limiter(rate_limiter)  # Подключаем лимитер
        .post_init(load_sent_posts)  # Загрузка данных при старте
        .post_shutdown(save_sent_posts)  # Сохранение данных при выходе (SIGTERM)
        .build()
    )

    # 3. Добавляем задачу мониторинга в очередь
    # run_repeating запускает monitor_website_job каждые 60 секунд
    # first=1 означает первый запуск через 1 секунду после старта
    application.job_queue.run_repeating(monitor_website, interval=180, first=1)

    # 4. Запускаем бота (Polling)
    # Это блокирующая операция, которая сама обрабатывает сигналы systemd
    print("Bot started via PTB Application")
    # Запуск с запросом на удаление вебхука и сброс накопившейся очереди
    application.run_polling(drop_pending_updates=True)
