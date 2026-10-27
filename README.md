# voice-note-service

Telegram-бот для подготовки структурированных заметок агента по недвижимости из голосовых сообщений.

Бот распознаёт речь через OpenAI Whisper и извлекает поля заметки локальной моделью через `llama.cpp`. CRM остаётся явной заглушкой до получения реального API-контракта.

## Стек

- Python 3.12
- aiogram 3.x
- OpenAI Whisper
- llama.cpp с локальной GGUF-моделью
- long polling
- aiogram `MemoryStorage` — данные текущей заметки живут только в памяти процесса

## Системная зависимость

Whisper использует `ffmpeg` для чтения Telegram OGG/Opus. Он должен быть установлен в системе и доступен в `PATH`.

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

## Локальный запуск без Docker

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env

export TELEGRAM_BOT_TOKEN="..."
export WHISPER_MODEL="small"

python -m bot.main
```

Перед обработкой голосовых сообщений без Docker установите `llama.cpp` и подготовьте GGUF-модель согласно `extractor/config/model.json`, затем запустите сервер через `python extractor/app/main.py`. При первом запуске Whisper скачает свои веса. Для локальной проверки на слабой машине можно временно выбрать меньшую модель через `WHISPER_MODEL`.

## Быстрый запуск на Ubuntu

Установите [Docker Engine и Compose plugin](https://docs.docker.com/engine/install/ubuntu/), затем из каталога проекта выполните:

```bash
./scripts/ubuntu-deploy.sh
```

Скрипт создаст `.env`, скрыто запросит токен Telegram, скачает небольшую GGUF-модель и запустит бота вместе с `llama.cpp`. Повторный запуск сохранит токен и уже скачанную модель. Для NVIDIA GPU после установки NVIDIA Container Toolkit используйте `./scripts/ubuntu-deploy.sh --gpu`.

Для тестов:

```bash
pip install -e '.[dev]'
pytest
```

## Что уже работает

- `/start` с короткой инструкцией пользователю;
- получение Telegram voice;
- подсказка о пересылке второго voice после завершения/отмены текущей заметки;
- скачивание аудио в bytes;
- локальное распознавание через Whisper;
- безопасный временный `.ogg` файл с гарантированным удалением;
- извлечение шести полей заметки через локальную модель;
- preview;
- редактирование лида, темы, описания, следующего шага, срока и дополнительной информации;
- запрет отправки в CRM без лида и темы; предупреждение о пустых рекомендуемых полях;
- confirm/cancel flow;
- in-memory состояние;
- обработка ошибок без логирования содержимого пользовательских данных;
- unit-тесты orchestration-логики.

## Извлечение полей заметки

`NoteExtractionService` вызывает локальную модель в worker thread и переводит её результат в поля заметки. Лидом служит адрес объекта или номер телефона человека. Если модель не нашла лид или тему, пользователь добавляет их вручную перед отправкой; тестовые значения не подставляются.

«Описание», «Следующий шаг» и «Срок» рекомендуются: бот предупреждает, если они пусты, но не блокирует отправку. «Дополнительная информация» необязательна.

## Что пока является заглушкой

### CRM

`CRMService.create_note()` не угадывает неизвестный API и явно сообщает, что CRM не настроена. После получения CRM-контракта здесь должны появиться:

- связь Telegram-аккаунта с CRM;
- авторизация;
- определение нужного клиента/контакта/сделки;
- создание заметки.

Подробные требования и границы текущей реализации находятся в [`telegram_voice_notes_bot_spec.md`](telegram_voice_notes_bot_spec.md).

## Развёртывание на Ubuntu

Для сервера нужны Git, Docker Engine с Compose plugin, `curl`, доступ к GitHub Container Registry и Hugging Face. Установка Docker описана в [официальной инструкции для Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Запускайте команды от пользователя с доступом к Docker; скрипт не устанавливает системные пакеты и не требует `sudo`.

```bash
git clone https://github.com/DIvanCode/voice-note-service.git
cd voice-note-service
./scripts/ubuntu-deploy.sh
```

При первом запуске скрипт создаёт `.env` с правами `600`, скрыто запрашивает `TELEGRAM_BOT_TOKEN`, скачивает [Qwen3-0.6B-Q8_0.gguf](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/tree/main) в `extractor/models/` и запускает Compose. По умолчанию Whisper использует `small`, а `llama.cpp` — небольшую модель 0.6B и контекст 2048. Это настройки для первого запуска на ограниченных ресурсах; качество извлечения на вашей задаче нужно проверить на собственных голосовых сообщениях.

Compose использует готовый [официальный образ `llama.cpp`](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md), поэтому клонировать и собирать `llama.cpp` на сервере больше не требуется. Модель хранится отдельно от образа, веса Whisper — в томе `whisper_cache`, а расшифровки — в `data/transcriptions.log`. Бот работает через Telegram long polling: открывать входящий порт не нужно. Сервис бота стартует после проверки готовности модели.

### Другая модель или NVIDIA GPU

Чтобы использовать свой GGUF-файл, скопируйте его в `extractor/models/`, укажите имя файла в `.env` через `MODEL_FILE` и повторно запустите скрипт. Существующий файл скрипт не скачивает заново.

Для NVIDIA GPU сначала установите драйвер и [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). Затем выполните:

```bash
./scripts/ubuntu-deploy.sh --gpu
```

Этот режим использует готовый образ `server-cuda` и параметр `LLAMA_GPU_LAYERS` из `.env`. Если нужна другая версия CUDA или специальная сборка, можно указать свой образ через `LLAMA_CUDA_IMAGE` в `.env`. CPU-образ аналогично переопределяется через `LLAMA_IMAGE`.

### Проверка и управление

```bash
docker compose ps
docker compose logs -f bot llama
docker compose restart
docker compose down
```

Для GPU-режима добавляйте к командам `docker compose` параметры `-f compose.yaml -f compose.cuda.yaml`. Чтобы обновить код и перезапустить сервисы, выполните `git pull` и снова `./scripts/ubuntu-deploy.sh` (или с `--gpu`). Скрипт сохранит существующий `.env` и модель.

CRM пока остаётся заглушкой: бот подготовит заметку, но не сохранит её в реальную CRM.
