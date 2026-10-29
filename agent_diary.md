# Дневник: профиль GitHub YouRooni

## 2026-10-29
- Референс: metawka/expressive-profile. Там весь профиль из SVG-баннеров, взяли меру: шапка + 4 карточки проектов, остальное обычный markdown.
- `scripts/build.py` собирает `assets/*.svg` (светлая и тёмная версии). Шрифты DM Sans / DM Mono режутся до нужных букв и вшиваются woff (brotli не нужен).
- Формы M3E из `m3-expressive-studio/shapes`, иконки Material Symbols Rounded в `icons/`.
- Аватарка вшивается base64 в шапку (GitHub не грузит внешние картинки внутри SVG). Сменил аву: перезапустить сборку или workflow.
- Звёзды и язык берутся из API одним запросом; при лимите 403 берётся кеш `tmp/repos.json`. Ноль звёзд не показываем.
- Workflow `.github/workflows/build.yml` пересобирает раз в сутки.
- Превью: сервер `profile-preview` в `E:\VSC\.claude\launch.json`, страница `tmp/preview.html`.
