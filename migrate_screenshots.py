#!/usr/bin/env python3
import sqlite3

DB_PATH = "/app/data/camera.db"
print(f"🔍 Миграция таблицы screenshots в {DB_PATH}...")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Проверяем текущие колонки
c.execute("PRAGMA table_info(screenshots)")
current_cols = [r[1] for r in c.fetchall()]
print(f"📋 Текущие колонки: {current_cols}")

# Колонки для добавления
new_cols = [
    ("ollama_response", "TEXT"),
    ("motion_level", "INTEGER DEFAULT 0"),
    ("is_danger", "BOOLEAN DEFAULT 0"),
    ("original_path", "VARCHAR(255)"),
    ("resized_path", "VARCHAR(255)"),
]

for col_name, col_def in new_cols:
    if col_name in current_cols:
        print(f"ℹ️ Уже есть: {col_name}")
    else:
        try:
            sql = f"ALTER TABLE screenshots ADD COLUMN {col_name} {col_def}"
            print(f"🔧 Выполняю: {sql}")
            c.execute(sql)
            print(f"✅ Добавлено: {col_name}")
        except Exception as e:
            print(f"❌ Ошибка {col_name}: {e}")

conn.commit()

# Финальная проверка
c.execute("PRAGMA table_info(screenshots)")
final_cols = [r[1] for r in c.fetchall()]
print(f"📋 Итоговые колонки: {final_cols}")
conn.close()
print("✅ Миграция screenshots завершена!")
