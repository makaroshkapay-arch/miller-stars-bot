import os
import re

# Путь к папке проекта
project_path = r"c:\Users\makar\OneDrive\Desktop\бот"

# Файлы для проверки
files_to_check = []

for root, dirs, files in os.walk(project_path):
    for file in files:
        if file.endswith('.py'):
            files_to_check.append(os.path.join(root, file))

for file_path in files_to_check:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие импорта db
    if 'from database.core import db' in content and 'get_db' not in content:
        print(f"Найден старый импорт в: {file_path}")
        
        # Заменяем импорт
        content = content.replace(
            'from database.core import db',
            'from database.core import get_db'
        )
        
        # Сохраняем файл
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Исправлен: {file_path}")