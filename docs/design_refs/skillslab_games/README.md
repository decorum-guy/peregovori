# Источник локального каталога

Страница скачана напрямую 14 октября 2026 года: https://exercises.skillslab.center/games.

`original.html` — неизменённый HTTP HTML. Это оболочка React: видимые карточки появляются из JS. `original-rendered.html` — фактическая DOM-разметка шести игр, сохранённая из браузера. `original-catalog.css` — исходные правила `.gh-*` и `.lang-switch`, извлечённые из скачанного stylesheet.

Локальная копия находится в `web/catalog/index.html`. Шесть карточек заменены одной «Линия решения»; у неё «Л» и цвет #AE432F. Сохранены зелёный градиент, затемнение, размеры/радиусы и hover: подъём 4 px, обводка, тень, 140 мс. `auto-fill` вместо `auto-fit` сохраняет ширину карточки при одном элементе. Нормализация CSS повторяет эффективные базовые стили оригинала. RU/EN переключает только каталог; игра остаётся на русском.

Логотип сохранён локально; сторонние игры, их JS bundle, внешние шрифты и API не подключаются. Копия открывается через наш FastAPI на `/games`, карточка ведёт на `/games/line-decision`. Оригинальный сайт не изменён.

| Скачать | Размер, bytes | SHA-256 |
|---|---:|---|
| https://exercises.skillslab.center/games | 486 | `2c891db2a84f263da8f41df482d3d149096c8b2b300fb4feb0235b4df70a54b7` |
| https://exercises.skillslab.center/assets/index-CWDoVKxk.css | 268797 | `c231170dda2e2d2fbd6da70fcf055b83e02fe06e41b3d520b9839dc29b1d909f` |
| https://exercises.skillslab.center/assets/index-DiiwJ1A6.js | 1691679 | `406e9f98226e289601c6f742c15f697cce4533826ab5aa88bdb6cf21ad2ec5c3` |
| https://exercises.skillslab.center/logo_light.svg | 77031 | `79bb837a48d080a42e84ea51cdcddd7bef6263e0f36134dc879893184f02c2fe` |
