#!/usr/bin/env python3
"""Bounded, explicit network checks. A Mac/proxy check cannot prove Russian ISP access."""
import argparse
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from _demo import ROOT
import httpx
from app.config import Settings


def check_network(proxy):
    results = []
    with httpx.Client(proxy=proxy or None, trust_env=False, timeout=5) as client:
        for label, url in [('Quick Tunnel API / HTTPS', 'https://api.trycloudflare.com')]:
            try:
                response = client.get(url)
                # GET / is allowed to return 405: successful TLS/HTTP is the check here.
                print('%s: HTTP %d (это проверка соединения, не готового туннеля)' % (label, response.status_code))
                results.append(response.status_code < 500)
            except httpx.HTTPError as exc:
                print('%s: %s; соединение не подтверждено.' % (label, type(exc).__name__))
                results.append(False)
    # The edge is not an ordinary HTTP origin; a failed GET there does NOT prove
    # a blocked port. Validate TCP here, and the actual TLS tunnel with --start.
    for host in ('region1.v2.argotunnel.com', 'region2.v2.argotunnel.com'):
        try:
            with socket.create_connection((host, 7844), timeout=5):
                print('%s: прямой TCP 7844 доступен; TLS Tunnel проверяется самим cloudflared.' % host)
                results.append(True)
        except OSError:
            print('%s: прямой TCP 7844 не подтверждён.' % host)
            results.append(False)
    if proxy:
        print('HTTP-прокси проверен для API. Маршрут edge при HTTP(S)_PROXY проверяется настоящим клиентом в --start.')
    return all(results)


def check_site(url, proxy):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        print('Нужен публичный HTTPS URL без credentials.')
        return False
    try:
        with httpx.Client(proxy=proxy or None, trust_env=False, timeout=8, follow_redirects=True) as client:
            root = client.get(url.rstrip('/') + '/')
            health = client.get(url.rstrip('/') + '/api/health')
            ok = root.status_code == 200 and 'id="root"' in root.text and health.status_code == 200 and health.json().get('status') == 'ok'
        print('Публичный frontend и /api/health: ' + ('работают с этой машины/маршрута.' if ok else 'не подтверждены.'))
        return ok
    except (httpx.HTTPError, ValueError, AttributeError):
        print('Публичный сайт с этого маршрута не отвечает корректно.')
        return False


def try_tunnel(binary, proxy):
    # --start is explicit publication of the local demo, for at most 35 seconds.
    env = {key: value for key, value in os.environ.items() if key.lower() not in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}}
    if proxy:
        env.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, NO_PROXY='127.0.0.1,localhost')
    process = None
    try:
        with tempfile.TemporaryFile(mode='w+') as log:
            process = subprocess.Popen([binary, 'tunnel', '--no-autoupdate', '--protocol', 'http2', '--url', 'http://127.0.0.1:8000'],
                                       stdout=log, stderr=log, env=env)
            deadline, url = time.monotonic() + 35, None
            while time.monotonic() < deadline:
                time.sleep(0.5)
                log.seek(0)
                data = log.read()
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', data)
                if match:
                    url = match[0]
                if url and 'Registered tunnel connection' in data:
                    print('Тестовая ссылка: ' + url)
                    return check_site(url, proxy)
                if process.poll() is not None:
                    break
            print('cloudflared не подтвердил Tunnel за 35 секунд. ' + ('Адрес был выделен, но подключение edge не подтверждено.' if url else 'Публичный адрес не получен.'))
            print('HTTP(S)_PROXY для этого запуска задан: %s. Его наличие не доказывает проксирование edge:7844.' % bool(proxy))
            return False
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy', action='store_true', help='Explicitly test with OPENROUTER_PROXY_URL; does not change the app')
    parser.add_argument('--public-url', help='Check an already-created public HTTPS site')
    parser.add_argument('--start', action='store_true', help='Temporarily publish localhost:8000, test and stop this test tunnel')
    parser.add_argument('--cloudflared', default=shutil.which('cloudflared'), help='Path to an already-installed official binary')
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.validate()
    proxy = settings.openrouter_proxy_url if args.proxy else ''
    if args.proxy and not proxy:
        print('Для --proxy задайте OPENROUTER_PROXY_URL в web/.env.')
        return 1
    print('Маршрут проверки: ' + ('заданный HTTP(S)-прокси.' if proxy else 'прямой.'))
    ok = check_network(proxy)
    if args.public_url:
        ok = check_site(args.public_url, proxy)
    if args.start:
        if not args.cloudflared:
            print('cloudflared отсутствует. Установите официальный клиент или используйте --cloudflared PATH.')
            ok = False
        else:
            ok = try_tunnel(args.cloudflared, proxy)
    print('Доступ из отдельной российской сети НЕ проверен. Откройте ссылку с российского мобильного интернета без VPN/прокси.')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
