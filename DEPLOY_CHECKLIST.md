# Запуск проекта на другом ПК (новый venv)

## Что сохраняется

Все изменения по Unfold и админке лежат в файлах проекта (не в venv):

| Файл | Назначение |
|------|------------|
| `requirements.txt` | django-unfold и остальные зависимости |
| `chistotut/settings.py` | UNFOLD, THEME, COLORS, STYLES, TIME_ZONE |
| `core/dashboard.py` | График заказов на главной админки |
| `core/admin.py` | Регистрация моделей через unfold.admin |
| `customer/admin.py` | Импорт ModelAdmin из unfold |
| `templates/admin/index.html` | Шаблон главной админки с графиком |
| `static/css/admin_unfold_borders.css` | Тени вместо границ в админке |

Папка `venv/` в репозиторий не входит (есть в `.gitignore`). На новом ПК venv создаётся заново.

## Шаги на новом ПК

1. Клонировать репозиторий (или скопировать проект).
2. Создать виртуальное окружение:
   ```bash
   python -m venv venv
   ```
3. Активировать venv:
   - Windows: `venv\Scripts\activate`
   - Linux/macOS: `source venv/bin/activate`
4. Установить зависимости:
   ```bash
   pip install -r requirements.txt
   ```
5. При необходимости применить миграции и создать суперпользователя:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
6. Запуск:
   ```bash
   python manage.py runserver
   ```

После этого админка с Unfold, графиком заказов, цветом #0d9488, светлой темой и тенями будет работать так же.

## Перед переносом: закоммитить изменения

Чтобы все правки попали на другой ПК через git, нужно их закоммитить и запушить:

```bash
git add requirements.txt chistotut/settings.py core/admin.py core/dashboard.py customer/admin.py templates/admin/index.html static/css/admin_unfold_borders.css
git commit -m "Unfold admin: дашборд с графиком заказов, тема, тени"
git push
```

Файл `db.sqlite3` лучше не коммитить (добавить в `.gitignore`). На новом ПК после `migrate` база будет пустой — создайте суперпользователя заново.
