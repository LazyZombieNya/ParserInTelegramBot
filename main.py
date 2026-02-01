import asyncio
import signal
import html
import os
import pickle
import platform
import shutil
from collections import deque, defaultdict
from io import BytesIO
from urllib.parse import urlparse

import aiofiles
import aiohttp
import ffmpeg
import httpx
from PIL import Image
from dotenv import load_dotenv
from telegram import Bot, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, ApplicationBuilder, ContextTypes, AIORateLimiter
from telegram.request import HTTPXRequest
from google import genai

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

# Ограничения Telegram
LIMIT_CAPTION = 400 #1024 # Лимит символов описания поста телеграмм
LIMIT_TEXT_MSG = 4096  # Лимит символов для одного сообщения телеграмм
MAX_MEDIA_PER_GROUP = 10  # Лимит Telegram на медиа-группу
MAX_SIZE_IMG_MB = 10  # Максимальный размер фото в MB
MAX_SIZE_VIDEO_MB = 50  # Максимальный размер видео в MB


# Списки
LIMIT = 40 #Лимит прогрузки постов по одному тегу
DATA_FOLDER = "temp_data"  # Папка где хранятся временно скачанные файлы
SAVE_FILE = "sent_posts.pkl" # Файл данными об отправленных постах
MAX_POSTS_SAVE = 150 #Количество постов для сохранения в отправленных
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Папка, где лежит main.py

posts = []  # Неотправленные посты
sent_posts = defaultdict(lambda: deque(maxlen=MAX_POSTS_SAVE))  # ID отправленных постов (отдельно для каждого сайта) с авто удалением старых записей

# Инициализация Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# FFmpeg мультимедийный фреймворк для работы с медиафайлами
if platform.system() == "Windows":
    FFMPEG_PATH = os.path.join(BASE_DIR, "lib", "ffmpeg.exe") #https://ffmpeg.org/download.html
    if not os.path.exists(FFMPEG_PATH):
        raise FileNotFoundError(f"FFmpeg not found at path {FFMPEG_PATH}, download it: https://ffmpeg.org/download.html")
else:
    # В Linux проверка, доступен ли ffmpeg в системном PATH
    if shutil.which("ffmpeg") is None: #Проверяет, есть ли исполняемый файл ffmpeg в переменной окружения PATH
        raise FileNotFoundError(
            "FFmpeg not found in PATH. Install it: sudo apt install ffmpeg -y"
        )
    FFMPEG_PATH = "ffmpeg"


# Устанавливаем таймауты (убираем ошибку timeout)
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
                #print(f"sent_posts: {sent_posts}")
    except FileNotFoundError:
        print("File with saved posts not found, create a new one.")
    except Exception as e:
        print(f"Error loading: {e}")
#Сохранение отправленных постов sent_posts в файл SAVE_FILE
async def save_sent_posts(app: Application):
    print("Saving data before exiting...")

    # Преобразуем defaultdict в обычный dict, иначе pickle не сможет его сохранить
    normal_dict = {key: list(value) for key, value in sent_posts.items()}
    try:
        async with aiofiles.open(SAVE_FILE, "wb") as file:
            await file.write(pickle.dumps(normal_dict))
        print("Data saved successfully!")
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

# Функция отправки постов в Телеграм
async def send_posts():
    global posts

    if not posts:
        #print("Нет новых постов для отправки.")
        await clear_data_folder() #Если все посты отправлены, то скачанные можно удалять
        return

    for post in posts[:]:  # Копия списка, чтобы можно было изменять оригинал
        first = True
        media_group = []
        animations = []  # Список для GIF-анимаций
        title_post = await generate_description_from_tags(post["title"])
        if not title_post.strip():  # если пусто или только пробелы
            title_post = post["title"]
        caption_full = f'<a href="{post["post_url"]}">Пост {post["post_id"]}</a> : {title_post}'  # Эта будет ссылкой на пост
        caption_post = caption_full[:LIMIT_CAPTION] + "..." if len(caption_full) > LIMIT_CAPTION else caption_full #Обрезаем длину Caption если доходит до лимита
        ext_file = get_file_extension(post['file_url'])
        if post["tag"] in TAGS_34_T:
            TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID_T
        if post["tag"] in TAGS_34_V:
            TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID_V

        #Картинки
        if ext_file in("jpeg","jpg","png"):
            match post["send"]:
                case "not": # Файл еще не отправлялся
                    media_group.append(InputMediaPhoto(media=post["file_url"],
                                            caption=caption_post if first else None,
                                            parse_mode="HTML"))
                case "err": # Файл отправляли, была ошибка
                    downloaded_file = await download_media(post["file_url"])
                    if downloaded_file:
                        with open(downloaded_file, 'rb') as file:
                            media_group.append(InputMediaPhoto(
                                media=file.read(),
                                caption=caption_post if first else None,
                                parse_mode="HTML"))
                    else:
                        post["send"] = "close"
        #Видео
        elif ext_file == "mp4":
            match post["send"]:
                case "not":
                    media_group.append(InputMediaVideo(media=post["file_url"],
                                                       caption=caption_post if first else None,
                                                       parse_mode="HTML"))
                case "err":
                    downloaded_file = await download_media(post["file_url"])
                    if downloaded_file:
                        with open(downloaded_file, 'rb') as file:
                            media_group.append(InputMediaVideo(
                                media=file.read(),
                                caption=caption_post if first else None,
                                parse_mode="HTML"))
                    else:
                        post["send"] = "close"
        #GIF файлы
        elif ext_file == "gif":
            match post["send"]:
                case "not":
                    animations.append(post["file_url"])
                case "err": #GIF файлы если не удалось отправить когда качаем мы его конвертируем в видео MP4
                    downloaded_file = await download_media(post["file_url"])
                    if downloaded_file:
                        with open(downloaded_file, 'rb') as file:
                            media_group.append(InputMediaVideo(
                                media=file.read(),
                                caption=caption_post if first else None,
                                parse_mode="HTML"))
                    else:
                        post["send"] = "close"
        else:
            post["send"] = "close"
            sent_posts[post["tag"]].append(post["post_id"])
            posts.remove(post)
            continue  # Пропускаем неизвестные форматы

        first = False  # Сбрасываем флаг после первого элемента

        if media_group:
            try:#Отправка медиа файлов
                    await bot.send_media_group(chat_id=TELEGRAM_CHAT_ID, media=media_group)
                    post["send"] = "yes"
            except Exception as e:
                if post["send"] == "not":
                    post["send"] = "err"
                else:
                    post["send"] = "close"
                print(f'Error sending post {post["post_id"]}: {e}')

        if animations:
            try:
                # Отправка анимаций GIF по отдельности
                    for animation in animations:
                        await bot.send_animation(chat_id=TELEGRAM_CHAT_ID, animation=animation,
                                                 caption=caption_post,
                                                 parse_mode="HTML")
                        post["send"] = "yes"
            except Exception as e:
                if post["send"] == "not":
                        post["send"] = "err"
                else:
                    post["send"] = "close"
                print(f'Error sending post {post["post_id"]}: {e}')


        if post["send"] in {"yes", "close"}:
            # Добавляем в список отправленных и удаляем из текущего списка
            sent_posts[post["tag"]].append(post["post_id"])  # помечаем что пост отправлен
            posts.remove(post)  # Удаляем только отправленный пост
            if post["send"] == "close":
                # Раз никак не удалось отправить пост то отправляем просто ссылку на пост и его теги
                IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "bmp", "webp"}
                ext = get_file_extension(post["file_url"]).lower()
                img_caption = "🖼 Файл изображения" if ext in IMAGE_EXTENSIONS else "📺 Видео файл"
                caption_dont_send = f'<a href="{post["file_url"]}">{img_caption} не загрузился, вот ссылка</a> \n\n {caption_post}'
                caption_dont = caption_dont_send[:LIMIT_CAPTION] + "..." if len(
                    caption_dont_send) > LIMIT_CAPTION else caption_dont_send  # Обрезаем длину Caption если доходит до лимита
                try:
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=caption_dont, parse_mode="HTML")
                except Exception as e:
                    print(f"Error sending message: {e}")
        await asyncio.sleep(10)  # Чтобы не спамил


async def generate_description_from_tags(tags: str) -> str:
    prompt = f"""Ты — бот, создающий описание по тегам.
    Вот список тегов: {tags}.
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
        print(f"Gemini error: {gemini_error}")

    # 2. Fallback на GROQ
    try:
        return await generate_with_groq(prompt)
    except Exception as groq_error:
        print(f"GROQ error: {groq_error}")
        return ""

    # try:
    #     response = await asyncio.to_thread(
    #         client.models.generate_content,
    #         model=GEMINI_MODEL,
    #         contents=prompt,
    #     )
    #
    #     if response and getattr(response, "text", None):
    #         return response.text.strip()
    #
    #     return ""
    # except Exception as e:
    #     print(f"Ошибка генерации описания: {e}")
    #     return ""

async def generate_with_groq(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        #"max_tokens": 40,  # примерно 20–25 слов на русском
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GROQ_URL, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


# Удаляет все файлы в папке DATA_FOLDER, если они есть.
async def clear_data_folder():
    if os.path.exists(DATA_FOLDER):
        for file in os.listdir(DATA_FOLDER):
            file_path = os.path.join(DATA_FOLDER, file)
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

#Сжатие картинок если они больше MAX_SIZE_IMG_MB
async def compress_image(image_bytes, max_size=MAX_SIZE_IMG_MB * 1024 * 1024):
    img = Image.open(BytesIO(image_bytes))
    img = img.convert("RGB")  # Убираем прозрачность
    output = BytesIO()

    quality = 85  # Начальное качество JPEG
    while True:
        output.seek(0)
        img.save(output, format="JPEG", quality=quality)
        if output.tell() <= max_size or quality <= 10:
            break
        quality -= 5  # Уменьшаем качество

    return output.getvalue()

#Сжатие видео с помощью FFMPEG
async def compress_video(input_path, output_path):
    print(f"Compressing video: {input_path} -> {output_path}")

    command = [
        FFMPEG_PATH, "-y", "-i", input_path,
        "-vcodec", "libx264", "-crf", "28", "-preset", "fast",
        "-b:v", "1M", "-threads", "1", output_path
    ]

    # command = [
    #
    #     FFMPEG_PATH, "-y", "-i", input_path,
    #     "-vcodec", "libx264", "-crf", "28", "-preset", "fast",
    #     "-b:v", "1M", output_path
    # ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        print(f"Compression complete: {output_path}")
    else:
        print(f"Compression error! {stderr.decode()}")

    return os.path.exists(output_path)

#Функция конвертации Gif в Mp4
async def gif_to_mp4(input_path, output_path):
    ffmpeg.input(input_path).output(
        output_path, vcodec="libx264", crf=28, preset="fast"
    ).run(overwrite_output=True)
    return output_path

#Скачивает медиафайлы на диск со сжатием
async def download_media(url):
    headers = {  # Делаем шапку чтобы не ругался и не блокировали доступ к файлам
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/122.0.0.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Referer": url,  # Динамически подставляем URL
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }

    ext = get_file_extension(url)
    if ext == "jpg": ext = "JPEG"  # Pillow не поддерживает "JPG", только "JPEG"
    #filename = f"temp_{url.split('/')[-1].lower()[:50]}.{ext}"
    name_only = os.path.splitext(url.split("/")[-1])[0].lower() # имя файла без расширения, приведённое к нижнему регистру.
    filename = f"temp_{name_only[:40]}.{ext.lower()}"

    os.makedirs(DATA_FOLDER, exist_ok=True)  # Создаем папку Data, если её нет
    file_path = os.path.join(DATA_FOLDER, filename)

    try:
        async with aiohttp.ClientSession() as session:
            # Проверяем размер файла перед загрузкой (HEAD запрос)
            if ext in ['mp4', 'avi', 'mov', 'mkv', 'webm']:
                async with session.head(url, headers=headers) as head_response:
                    if head_response.status == 200:
                        content_length = head_response.headers.get('Content-Length')
                        if content_length:
                            file_size_mb = int(content_length) / (1024 * 1024)

                            # Примерная оценка: если файл больше MAX_SIZE_VIDEO_MB * 2,
                            # то даже после сжатия вряд ли уместится
                            # Можно настроить коэффициент (например, 1.5, 2, 3)
                            if file_size_mb > MAX_SIZE_VIDEO_MB * 2:
                                print(f"Видео слишком большое ({file_size_mb:.2f} MB), пропускаем: {url}")
                                return None
                            elif file_size_mb > MAX_SIZE_VIDEO_MB:
                                print(f"Видео {file_size_mb:.2f} MB, попробуем сжать")
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    file_bytes = await response.read()  # Скачиваем файл как байты

                    if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
                        compressed_bytes = await compress_image(file_bytes)
                        with open(file_path, 'wb') as img_file:
                            img_file.write(compressed_bytes)

                    elif ext in ['mp4', 'avi', 'mov', 'mkv', 'webm', 'gif']:
                        temp_path = file_path + "_temp" #Файл сперва скачиваем как _temp
                        async with aiofiles.open(temp_path, 'wb') as file:
                            await file.write(file_bytes)
                        if ext == "gif":  # Всегда конвертируем GIF → MP4
                            compressed_path = file_path.replace(".gif", ".mp4")
                            await gif_to_mp4(temp_path, compressed_path)
                        elif os.path.getsize(temp_path) < MAX_SIZE_VIDEO_MB * 1024 * 1024:  # Сжатие видео если больше MAX_SIZE_VIDEO_MB
                            #print(f"Видео {temp_path} меньше {MAX_SIZE_VIDEO_MB} МБ, сжатие не требуется.")
                            compressed_path = temp_path  # Используем как есть
                        else:
                            compressed_path = file_path
                            await compress_video(temp_path, compressed_path)

                        os.rename(compressed_path, file_path) # А потом как все операции с медиафайлом сделаны мы его переименуем, удаляем _temp
                    else:
                        print(f"Error: Unsupported file format {ext}")
                        return None

                    return file_path
                else:
                    print(f"Loading error: {response.status}")
    except Exception as e:
        print(f"Loading error: {file_path}: {e}")
        return None
    return None

# Узнаем какого разрешения файл по ссылке
def get_file_extension(url):
    parsed_url = urlparse(url)
    path = parsed_url.path.strip('/')  # Достаем путь из ссылки и убираем лишние слэши
    parts = path.rsplit('.', 1)  # Разделяем по последней точке на части

    if len(parts) == 2 and parts[1]:  # Если есть расширение (т.е. состоит из 2 частей) возвращаем в нижнем регистре
        return parts[1].lower()
    return ""  # Если расширения нет, возвращаем пустую строку


async def fetch_html(url):
    """Асинхронный запрос к сайту."""
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"Error loading site: {response.status}")
                return None  # Вернем None, если страница не загрузилась

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

    # Задержка перед следующей проверкой
    await asyncio.sleep(10)  # Проверяем каждые 60 секунд

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

    # Задержка перед следующей проверкой
    await asyncio.sleep(10)  # Проверяем каждые 60 секунд

async def monitor_website(context: ContextTypes.DEFAULT_TYPE):
    try:
        await monitor_website_34_T(context.application)
        await monitor_website_34_V(context.application)
        await send_posts()
        await asyncio.sleep(60)  # Ждём 60 секунд перед следующим запросом
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
    application.run_polling()
