# softskills.fun/games — домен REG.RU и локальный Mac (план подключения)

**Решение владельца 14.10.2026:** купленный домен `softskills.fun`, регистратор **REG.RU**; публичный каталог «Линии решения» — **https://softskills.fun/games**, игра — **https://softskills.fun/games/line-decision**. Не путать с опечаткой `softkills.fun`: настраивать только `softskills.fun`. Не использовать `game.softskills.fun`, если владелец отдельно не изменит выбор.

**СТАТУС:** имя и маршрут согласованы, но NS/DNS в REG.RU, Cloudflare zone/tunnel, Mac и внешняя HTTPS-ссылка **не настроены и не проверены этим чатом**. Это конфигурационная инструкция, **не отчёт об успешном деплое**.

## Что подтверждено по коду

- `web/backend/app/main.py` уже обслуживает `GET /games` и `GET /games/line-decision`.
- `scripts/start_demo_mac.sh` запускает FastAPI на `127.0.0.1:8000`, а `scripts/start_domain_demo.sh` — предварительно настроенный `cloudflared`.
- `deploy/cloudflared.demo.example.yml` направляет **все пути выбранного hostname** на `http://127.0.0.1:8000`; НЕ надо добавлять `/games` в поле hostname или service. `/assets`, `/api/*` и страницы останутся на одном origin.
- `DEMO_ACCESS_CODE` в локальном `web/.env` защищает страницы/API через Basic username `demo`. `/api/health` намеренно остаётся публичной диагностикой.

## A. Проверка DNS и сохранение записей

1. В REG.RU открыть **Домены → softskills.fun → DNS-серверы и управление зоной**. Проверить текущие NS, есть ли рабочие сайт/почта, и сохранить текущие A/AAAA/CNAME/MX/TXT/CAA, если они используются. **Не менять NS вслепую**: перенос NS без переноса записей может повредить текущие сервисы.
2. Добавить `softskills.fun` как DNS-зону в аккаунт Cloudflare (обычный Full setup), проверить импорт записей и получить **два NS из панели Cloudflare**. Не угадывать NS.
3. В REG.RU выбрать свой список DNS-серверов и вставить именно выданные Cloudflare NS; дождаться подтверждения `Active` в Cloudflare. Делегирование может занять время. Если домен уже использует Cloudflare DNS, повторная смена не нужна.
4. Cloudflare Named Tunnel поддерживает apex/root `softskills.fun`, используя CNAME flattening. При создании маршрута не должен оставаться конфликтующий A/AAAA/CNAME для `@`; проверить существующие записи и назначение до удаления.

Источники: [Cloudflare Tunnel FAQ (apex domain)](https://developers.cloudflare.com/cloudflare-one/faq/cloudflare-tunnels-faq/), [Cloudflare DNS route](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/), [Cloudflare apex DNS](https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-zone-apex/), [REG.RU DNS and NS](https://help.reg.ru/support/dns-servery-i-nastroyka-zony/rabota-s-dns-serverami/).

## B. QA Mac — до DNS/публичной публикации

Сначала проверить свежий GitHub HEAD и локальные изменения, не делать force reset и не заменять секреты. Выполнить существующее QA-задание `prompts/CODEX_VERIFY_SOL_DEMO_ON_MAC_2026-10-14.md`: тесты backend/compileall/frontend build, конфигурация Sol Generator + Sol Roleplayer + Luna Judge, проверка маршрутов без платных вызовов. Сохранить действующий `OPENROUTER_API_KEY` и `OPENROUTER_PROXY_URL`, только дополнить существующий ignored `web/.env`.

Владелец сам играет новую реальную Sol/Sol/Luna сессию на `http://127.0.0.1:8000/games`, после неё по желанию запускает Luna Judge. Фиксировать **реальные** результат и расходы, не брать исторические $0.04635 за цену новой игры.

## C. Настройка именованного туннеля

После проверки исходящего Cloudflare edge на Mac и активной DNS-зоны:

```bash
cloudflared tunnel login
cloudflared tunnel create line-decision-demo
cloudflared tunnel route dns line-decision-demo softskills.fun
cp deploy/cloudflared.demo.example.yml web/cloudflared.local.yml
```

Локально, **без коммита**, заполнить `web/cloudflared.local.yml`:

```yaml
tunnel: <UUID_ИЗ_КОМАНДЫ_CREATE>
credentials-file: /Users/<MAC_USER>/.cloudflared/<UUID_ИЗ_КОМАНДЫ_CREATE>.json
protocol: http2

ingress:
  - hostname: softskills.fun
    service: http://127.0.0.1:8000
  - service: http_status:404
```

`<...>` в примере — реальные значения при настройке. Файл credentials JSON, tunnel token, API key, proxy credentials, `web/.env` и SQLite **не коммитить**.

Перед внешним показом задать сильный непубличный `DEMO_ACCESS_CODE` в `web/.env`. В двух терминалах Mac:

```bash
bash scripts/start_demo_mac.sh
# в другом терминале:
bash scripts/start_domain_demo.sh web/cloudflared.local.yml --check
bash scripts/start_domain_demo.sh
```

**Не указывать `/games` в YAML ingress:** backend уже знает этот путь. HTTPS-конечный адрес должен быть `https://softskills.fun/games`, а не `https://game.softskills.fun/games`.

## D. Критерии реальной публикации

- HTTPS-сертификат браузером принят, `https://softskills.fun/games` открывает каталог, карточка ведёт в `/games/line-decision`, API доступен с того же origin.
- Без Basic credentials — 401; с логином `demo` и секретным паролем — 200; не публиковать код вместе с URL. Проверить лимиты, что OpenRouter key не возвращается в ответах.
- Mac остаётся включён, не засыпает; OpenRouter proxy работает; tunnel процесс жив; **Intelion inference/локальный Qwen порт не доступны извне**.
- Проверка другого устройства и сети **подруги, желательно из РФ без VPN**, успешное создание и продолжение реальной игры с сохранением сессии. Успех с одного Mac через прокси не считается.
- До подтверждения владельца **не закрывать Issue #11**; при недоступном из РФ Cloudflare оставить issue открытым и задокументировать блокер. Перед встречей с Юрием иметь запасную локальную запись.
