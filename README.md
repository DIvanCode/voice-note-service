# voice-note-service

Telegram-бот для подготовки структурированных заметок агента по недвижимости из голосовых сообщений.

Текущая версия уже выполняет локальное распознавание речи через OpenAI Whisper. Вторая ML/LLM-модель пока заменена предсказуемой тестовой реализацией, а CRM остаётся явной заглушкой до получения реального API-контракта.

## Стек

- Python 3.12
- aiogram 3.x
- OpenAI Whisper
- long polling
- aiogram `MemoryStorage` — данные текущей заметки живут только в памяти процесса

## Системная зависимость

Whisper использует `ffmpeg` для чтения Telegram OGG/Opus. Он должен быть установлен в системе и доступен в `PATH`.

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

## Запуск

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env

export TELEGRAM_BOT_TOKEN="..."
export WHISPER_MODEL="large"

python -m bot.main
```

При первом запуске Whisper скачает веса выбранной модели. Модель загружается один раз при старте приложения и затем переиспользуется для всех сообщений. Для локальной проверки на слабой машине можно временно выбрать меньшую модель через `WHISPER_MODEL`.

## Запуск в Docker Compose

В `compose.yaml` описан один контейнер бота. Укажите `TELEGRAM_BOT_TOKEN` и `WHISPER_MODEL` в `.env` (пример — `.env.example`). Для VM с ограниченной памятью начните с `WHISPER_MODEL=base`; модель `large` требует значительно больше RAM.

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f bot
```

Бот использует Telegram long polling, поэтому открывать порт не нужно. Распознанный текст добавляется в `data/transcriptions.log`, а скачанные веса Whisper сохраняются в томе `whisper_cache` между пересозданиями контейнера. Для контейнера не задан жёсткий лимит CPU или RAM: он может использовать доступные ресурсы VM. Docker не увеличивает объём памяти VM.

Для тестов:

```bash
pip install -e '.[dev]'
pytest
```

## Что уже работает

- `/start` с короткой инструкцией пользователю;
- получение Telegram voice;
- блокировка второго voice до завершения/отмены текущей заметки;
- скачивание аудио в bytes;
- локальное распознавание через Whisper;
- безопасный временный `.ogg` файл с гарантированным удалением;
- временная text-to-note реализация;
- preview;
- редактирование темы, текста, ФИО и телефона;
- запрет отправки в CRM без темы;
- confirm/cancel flow;
- in-memory состояние;
- обработка ошибок без логирования содержимого пользовательских данных;
- unit-тесты orchestration-логики.

## Временная реализация второй модели

Пока настоящая модель структурирования текста не подключена, `NoteExtractionService` возвращает:

- `note` — исходный распознанный Whisper текст;
- `full_name` — `Тестовый Клиент`;
- `phone` — `+79990000000`;
- `topic` — `Тестовая тема`.

Благодаря этому можно проверить весь Telegram-flow и редактирование без второй нейронной сети.

## Что пока является заглушкой

### CRM

`CRMService.create_note()` не угадывает неизвестный API и явно сообщает, что CRM не настроена. После получения CRM-контракта здесь должны появиться:

- связь Telegram-аккаунта с CRM;
- авторизация;
- определение нужного клиента/контакта/сделки;
- создание заметки.

Подробные требования и границы текущей реализации находятся в [`telegram_voice_notes_bot_spec.md`](telegram_voice_notes_bot_spec.md).

## Развёртывание нейросети в Docker

Docker Compose запускает бота и `llama.cpp` как два сервиса в одной сети. Бот обращается к модели по внутреннему адресу `http://llama:8080`; отдельный запуск `python extractor/app/main.py` больше не требуется.

Модель в Docker-образ не включается. GGUF-файл хранится отдельно в каталоге `extractor/models/`, поэтому при переносе на другой сервер или замене Qwen3 не требуется пересобирать образ бота.

### Требования к серверу

На любом сервере нужны:

- Docker Engine с Docker Compose Plugin;
- достаточно места для Docker-образов и GGUF-файла;
- файл модели в формате GGUF;
- значение `TELEGRAM_BOT_TOKEN`.

Для NVIDIA GPU дополнительно нужны установленный драйвер NVIDIA и NVIDIA Container Toolkit. Docker должен видеть GPU до запуска проекта:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.8.1-runtime-ubuntu24.04 nvidia-smi
```

Вторая команда должна показать ту же видеокарту внутри контейнера. Если сервер работает без NVIDIA или GPU недоступен Docker, используйте обычный CPU-профиль.

### Подготовка проекта

Скопируйте проект и GGUF-модель на сервер:

```bash
git clone <repository-url> voice-note-service
cd voice-note-service
mkdir -p extractor/models data
cp /path/to/Qwen3-8B-Q4_K_M.gguf extractor/models/
cp .env.example .env
```

В `.env` задайте `TELEGRAM_BOT_TOKEN`. Имя `MODEL_FILE` должно совпадать с именем файла в `extractor/models/`. Остальные параметры можно менять без редактирования Python-кода:

```dotenv
MODEL_FILE=Qwen3-8B-Q4_K_M.gguf
LLAMA_CONTEXT=4096
LLAMA_BATCH=64
LLAMA_UBATCH=32
LLAMA_PARALLEL_SLOTS=1
LLAMA_GPU_LAYERS=999
WHISPER_MODEL=base
```

`LLAMA_GPU_LAYERS=999` означает попытку выгрузить на GPU все возможные слои. Если модель не помещается в VRAM, `llama.cpp` оставит часть слоёв в RAM. На сервере с другой видеокартой это значение можно изменить без пересборки приложения. `LLAMA_PARALLEL_SLOTS` задаёт количество параллельных слотов модели; увеличивайте его только после проверки RAM, VRAM и latency.

### Запуск на NVIDIA GPU

Для NVIDIA используется тот же базовый Compose-файл и аппаратный override:

```bash
docker compose -f compose.yaml -f compose.cuda.yaml up -d --build
```

CUDA-образ `llama.cpp` собирается из исходного дерева, которое находится в `extractor/llama.cpp`. Версии CUDA и Ubuntu задаются в `.env` через `CUDA_VERSION` и `UBUNTU_VERSION`. По умолчанию используется CUDA 12.8.1 и Ubuntu 24.04; при несовместимости с драйвером выберите поддерживаемую версию CUDA.

Проверка запуска:

```bash
docker compose -f compose.yaml -f compose.cuda.yaml ps
docker compose -f compose.yaml -f compose.cuda.yaml logs -f llama
```

Сервис `bot` запускается только после успешного healthcheck `llama.cpp`. В логах `llama` должны быть признаки загрузки CUDA backend и модели. Сам порт модели наружу не публикуется: он доступен только контейнеру бота.

### Запуск без NVIDIA GPU

На CPU-сервере используется базовый Compose-файл:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f llama
```

В этом режиме CUDA Toolkit и NVIDIA Container Toolkit не нужны. Для CPU может потребоваться меньшая GGUF-модель, меньшее значение `LLAMA_CONTEXT` или более консервативные `LLAMA_BATCH` и `LLAMA_UBATCH`.

### Перенос на другое железо

Исходный код бота, сетевой контракт и Compose-конфигурация остаются одинаковыми. При переносе меняются только `.env`, GGUF-файл и, если нужно, выбранный профиль:

```bash
# NVIDIA
docker compose -f compose.yaml -f compose.cuda.yaml up -d --build

# CPU
docker compose up -d --build
```

Текущая конфигурация собирает `llama.cpp` из исходников проекта, что сохраняет одинаковую версию и поведение на разных серверах. Локальная CUDA-архитектура не зашита в код бота; при необходимости её можно задать переменной `CUDA_DOCKER_ARCH`.

### Остановка и диагностика

```bash
# NVIDIA
docker compose -f compose.yaml -f compose.cuda.yaml down

# CPU
docker compose down
```

Если `bot` не запускается, сначала проверьте состояние модельного сервиса:

```bash
docker compose ps
docker compose logs --tail=200 llama
docker compose logs --tail=200 bot
```

Частые причины ошибки: отсутствующий файл `extractor/models/${MODEL_FILE}`, неподдерживаемая версия CUDA для драйвера, отсутствие `--gpus all` для NVIDIA-профиля или недостаток RAM/VRAM. После замены модели достаточно обновить `MODEL_FILE` и перезапустить Compose; образ бота пересобирать не требуется.
