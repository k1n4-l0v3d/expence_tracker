#!/bin/bash
# Локальный запуск: ./run.sh
# Требует наличия .env.local рядом с app.py

if [ ! -f .env.local ]; then
    echo "Ошибка: файл .env.local не найден."
    echo "Скопируй .env.local.example → .env.local и заполни значения."
    exit 1
fi

set -a
source .env.local
set +a

echo "Запуск на http://${FLASK_HOST:-127.0.0.1}:${FLASK_PORT:-5000}"
python3 app.py
