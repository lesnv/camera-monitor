#!/usr/bin/env python3
import sqlite3
import sys

DB_PATH = "/app/data/camera.db"

print(f"🔍 Подключаюсь к {DB_PATH}...")

try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    print("✅ Подключение успешно")
    
    # Проверяем текущие колонки
    c.execute("PRAGMA table_info(cameras)")
    current_cols = [r[1] for r in c.fetchall()]
    print(f"📋 Текущие колонки: {current_cols}")
    
    # Колонки для добавления
    new_cols = [
        ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ("motion_sensitivity", "INTEGER DEFAULT 50"),
        ("detection_threshold", "REAL DEFAULT 0.3"),
        ("min_motion_area", "INTEGER DEFAULT 500"),
    ]
    
    for col_name, col_def in new_cols:
        if col_name in current_cols:
            print(f"ℹ️ Уже есть: {col_name}")
        else:
            try:
                sql = f"ALTER TABLE cameras ADD COLUMN {col_name} {col_def}"
                print(f"🔧 Выполняю: {sql}")
                c.execute(sql)
                print(f"✅ Добавлено: {col_name}")
            except Exception as e:
                print(f"❌ Ошибка {col_name}: {e}")
    
    conn.commit()
    print("✅ Коммит выполнен")
    
    # Финальная проверка
    c.execute("PRAGMA table_info(cameras)")
    final_cols = [r[1] for r in c.fetchall()]
    print(f"📋 Итоговые колонки: {final_cols}")
    
    conn.close()
    print("✅ Готово!")
    
except Exception as e:
    print(f"❌ Критическая ошибка: {e}")
    sys.exit(1)
