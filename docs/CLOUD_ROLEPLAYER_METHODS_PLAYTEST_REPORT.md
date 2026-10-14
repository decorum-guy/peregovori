# Cloud methodology A/B/C — ограниченный Sol screening

**LIVE CHECKPOINTS, NOT FULL METHODOLOGY GAMES.** Выполнено после четырёхмодельной трёхролевой матрицы и двух гибридов. Модель только `openai/gpt-6.1-sol`. Это не Claude Opus/Sonnet A/B/C и не подтверждение результата старого Qwen14B эксперимента.

Source: `web/backend/app/cloud_methodology.py`, version `cloud-role-aware-methods-1.0`; явный variant A/B/C, production его не вызывает. A* = исходный A + общая spoken-dialogue-1.0; B* = A* + короткая role-aware проверка стадии/полномочий/условий; C* = B* +10 реальных техник YAML для режима с разрешением любых иных приёмов. Teacher/oracle и case teaching не включены.

Три фиксированных входа: negotiation turn5, personal turn3, public turn2. Для всех вариантов одни кейсы/история, medium/1600, temperature omitted. Два A* переиспользованы, семь новых POST = **$0.0796048**, внутри общего $5. [Матрица/хеши](premium_pipeline_2026-10-14/methods-matrix.json), [маскированные ответы](premium_pipeline_2026-10-14/blind-methods-review-input.json), [оценки](premium_pipeline_2026-10-14/blind-methods-ratings.json).

9/9 — полные ответы без обнаруженных критических нарушений, ремарок и коучинга. B* явнее удержал три дня резерва и зависимость от старта; B*/C* прямо отделили частное извинение от публичного восстановления. A* также соблюдал ограничения. Один reviewer, частичная маскировка, по одной пробе на режим — оснований объявить B/C лучше нет.

Средний фактический USD/checkpoint: A* .002269, B* .007139, C* .018379. Cache/reuse и разные объёмы входа не позволяют объявлять эти отношения универсальным множителем цены полной игры. Десять техник увеличили затраты; многоходовой выигрыш не проверен.

**Решение: production A сохраняется.** Полные независимые A/B/C игры, Claude-эксперимент по Issue#3, новая Qwen оценка и обучение — NOT TESTED. Для будущего TRAIN v2 передавать causal role/unknowns/limits acceptance tests, не вставлять десять техник по умолчанию. Полные результаты и стоимость: [pipeline report](PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md).
