# После QLoRA: скачать адаптер и запустить DEV на RTX 3090

**Важное:** приватный DEV уже создан и заморожен пользователем, но его архив НЕ хранится в публичном GitHub. Эти скрипты не генерируют тесты заново и не меняют TRAIN/DEV/TEST.

## 0. Проверка Intelion до платного перезапуска

На Mac можно выполнить уже использованную read-only команду Intelion SDK и проверить статус сервера 11425. Не нужно создавать новую VM. Перезапускаем **тот же самый** `Negotiation-Trainer` с его старым диском; если диск не сохранился, обучение восстановить из локального бэкапа, если он есть.

Пока VM выключена, подготовьте приватный DEV ZIP на Mac — он понадобится для тестов.

## 1. Запустить тот же Intelion server 11425 и проверить результаты

В JupyterLab → Terminal:

```bash
cd ~/peregovori
source .venv/bin/activate
git pull --ff-only
python training/check_result.py
ls -lh training/outputs/qlora_v1_bundle.tar.gz*
```

Проверка читает `final_status.json`, адаптер, архив, SHA-256 и последние 35 строк `run.log`. Если `CHECKS ALL PASS: True`, результат действительно сохранён. Если нет — **не начинать переобучение**, сначала пришлите вывод проверки.

**Скачать сразу:** в файловом браузере JupyterLab откройте `peregovori/training/outputs/`, правой кнопкой по `qlora_v1_bundle.tar.gz` → **Download**, затем по `qlora_v1_bundle.tar.gz.sha256` → Download; также скачайте `run.log` и `final_status.json`. Наличие файлов у Intelion не равно резервной копии на Mac.

Для Mac проверка архива из терминала:

```bash
cd ~/Downloads
shasum -a 256 qlora_v1_bundle.tar.gz
cat qlora_v1_bundle.tar.gz.sha256
```

Два хеша должны совпасть. Не скачивать полные 8B-веса, только LoRA-адаптер и логи.

## 2. Подготовить DEV — приватно, без GitHub

Через **JupyterLab Upload** положить замороженный DEV ZIP в `~/peregovori/eval_private/dev_frozen.zip`.

Выполнить:

```bash
cd ~/peregovori
source .venv/bin/activate
python -m pip install jsonschema
python evaluation/import_private_zip.py --zip eval_private/dev_frozen.zip --suite dev
```

Должно появиться 25 кейсов и 75 проб:
`eval_private/dev/cases.jsonl` и `eval_private/dev/probes.jsonl`.

**Не коммить DEV ZIP, кейсы, пробы, oracle и ответы на GitHub.** `eval_private/` уже находится в `.gitignore`. Если авторазбор архива не нашёл двух JSONL — показать список `unzip -l eval_private/dev_frozen.zip`, без содержимого приватных кейсов; подстроим импорт.

## 3. Перевооружить таймер ПОСЛЕ перезапуска

Старый файл `training/outputs/intelion_deadline.json` пережил выключение VM, но предыдущий watchdog-процесс — нет. Проверьте, что старый таймер не жив:

```bash
pgrep -af 'intelion_autostop.py _watch' || true
```

Только если watcher не запущен, **архивируйте** старый дедлайн и запустите новый:

```bash
mv training/outputs/intelion_deadline.json training/outputs/intelion_deadline_previous.json
python training/intelion_autostop.py arm --server-id 11425 --minutes 90
python training/intelion_autostop.py status
```

Если старый процесс обнаружен, не переименовывайте файл: остановите и уточните текущее состояние. Внутренний таймер лишь подстраховка, отдельно проверить отключённое автопродление и итоговый статус у Intelion.

Лучше включить новый watchdog СРАЗУ после проверки адаптера и до длительного ожидания загрузки DEV. Указанные 90 минут — бюджет после arming, не абсолютное время аренды.

## 4. DEV-инференс: базовая Qwen vs QLoRA на ОДНОЙ GPU

После успешного `check_result.py` и импорта DEV:

```bash
mkdir -p eval_private/results/dev
nohup .venv/bin/python -u evaluation/run_and_stop.py --server-id 11425 > eval_private/results/dev/pipeline.log 2>&1 < /dev/null &
tail -f eval_private/results/dev/pipeline.log
```

Скрипт загружает **одну** базовую Qwen3-8B в 4 битах и подключает LoRA. Для BASE временно выключает LoRA, для QLoRA включает; он НЕ держит две независимые полные модели в видеопамяти.

Результат каждого хода записывается сразу, поэтому при сбое работа частично сохраняется.

Выходные файлы:
- `eval_private/results/dev/base.jsonl`: 75 исходных ответов;
- `eval_private/results/dev/lora.jsonl`: 75 обученных ответов;
- `eval_private/results/dev/summary.json`: скорость, количество, форматные индикаторы;
- `eval_private/results/dev/blind_review.csv`: анонимные пары A/B с критериями oracle;
- `eval_private/results/dev/blind_key_PRIVATE.json`: ключ к A/B, держать отдельно от судьи;
- `eval_private/dev_outputs.tar.gz` и `.sha256`: архив результатов DEV;
- `eval_private/results/dev/pipeline.log`, `final_status.json`: диагностика.

После упаковки результатов скрипт отправит через Intelion API команду остановки VM, даже если тест упал. Отдельный watchdog попытается остановить VM по таймеру.

**Ограничение автоматизации:** вычисление ответов 150 раз и формирование blind_review автоматические, но семантические оценки `must`/`must_not`, логику конфликта и роль манипулятора должен проверить независимый LLM-судья или человек. `summary.json` не доказывает педагогическое превосходство модели. До получения сравнения DEV закрытые TEST_A/TEST_B не используем.

## 5. Забрать результаты

Если не успели скачать `dev_outputs.tar.gz` до автоматического останова, потребуется кратко запустить **тот же сервер** и забрать файл через JupyterLab. Данные останутся на диске при условии сохранения диска провайдером. Для оптимизации расходов можно скачать адаптер на Mac **до запуска DEV**, а результаты — сразу после завершения, пока API-остановка не произошла; для полной автономности обычно потребуется краткий перезапуск для выгрузки.

Не удаляйте сервер/диск до того, как **все** архивы и SHA сохранены на Mac и проверены.

## 6. Время и безопасность

Подходящий ограниченный прогон — 90 минут таймера, но реальное время 150 генераций заранее не гарантировано. Сначала подготовить DEV zip. API Intelion останавливает VM по server ID 11425, не удаляет её. Скрипты запуска не протестированы на фактическом GPU — при первой сессии смотрим первые логи.

Выдавать TEST-пробы модели для выбора параметров нельзя: они запечатаны для финального контроля.
