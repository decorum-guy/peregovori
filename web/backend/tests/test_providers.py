import asyncio
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from app.config import Settings
from app.providers import OpenRouterProvider, ProviderError


@contextmanager
def endpoint():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, self.headers.get('Authorization'), body))
            data = json.dumps({'choices': [{'message': {'content': 'Ответ тестового HTTP endpoint.'}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:%d' % server.server_port, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('proxied', [False, True])
def test_real_httpx_direct_and_http_proxy_routes(proxied, monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:1')
    with endpoint() as (url, requests):
        # In proxy mode the hostname deliberately cannot resolve. Only the proxy receives it.
        settings = Settings(openrouter_api_key='dummy-test-key', openrouter_base_url='http://unresolvable.invalid/api/v1' if proxied else url + '/api/v1',
                            openrouter_proxy_url=url if proxied else '')
        reply = asyncio.run(OpenRouterProvider(settings).complete(settings.premium_model, [{'role': 'user', 'content': 'Привет'}], purpose='test'))
    assert reply == 'Ответ тестового HTTP endpoint.'
    assert requests[0][0] == ('http://unresolvable.invalid/api/v1/chat/completions' if proxied else '/api/v1/chat/completions')
    assert requests[0][1] == 'Bearer dummy-test-key'
    assert requests[0][2]['model'] == settings.premium_model


@pytest.mark.parametrize('scheme', ['http', 'https'])
def test_http_and_https_proxy_configuration_is_supported(scheme):
    settings = Settings(openrouter_proxy_url=scheme + '://user:proxy-password@example.invalid:443')
    settings.validate()
    client = OpenRouterProvider(settings).client()
    asyncio.run(client.aclose())
    assert 'proxy-password' not in repr(settings)


@pytest.mark.parametrize('failure,code', [(httpx.ProxyError, 'proxy_unavailable'), (httpx.ConnectError, 'provider_unavailable'),
                                       (httpx.ConnectTimeout, 'provider_timeout')])
def test_network_errors_do_not_disclose_proxy_credentials(failure, code, monkeypatch, caplog):
    secret = 'http://user:PROXY_SECRET_SENTINEL@example.invalid:8080'

    async def fail(*_args, **_kwargs):
        raise failure(secret)

    monkeypatch.setattr(httpx.AsyncClient, 'request', fail)
    provider = OpenRouterProvider(Settings(openrouter_api_key='API_SECRET_SENTINEL', openrouter_proxy_url=secret))
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.complete(provider.settings.premium_model, [], purpose='test'))
    assert error.value.code == code
    assert 'PROXY_SECRET_SENTINEL' not in str(error.value) + caplog.text
    assert 'API_SECRET_SENTINEL' not in str(error.value) + caplog.text


@pytest.mark.parametrize('status,code', [(401, 'provider_auth'), (403, 'provider_auth'), (407, 'proxy_auth'), (402, 'provider_credits'),
                                      (404, 'provider_model_missing'), (429, 'provider_rate_limit'), (500, 'provider_response')])
def test_error_bodies_are_never_returned(status, code):
    with pytest.raises(ProviderError) as error:
        OpenRouterProvider.check_response(httpx.Response(status, text='SECRET_RESPONSE_SENTINEL'))
    assert error.value.code == code
    assert 'SECRET_RESPONSE_SENTINEL' not in str(error.value)


def test_bad_proxy_url_is_rejected_without_echoing_it():
    with pytest.raises(ValueError) as error:
        Settings(openrouter_proxy_url='socks5://user:SECRET@example.invalid:10808').validate()
    assert 'SECRET' not in str(error.value)


@pytest.mark.parametrize('body', [[], {'choices': []}, {'choices': [{'message': {'content': 42}}]}, {'choices': [{'message': {'content': ''}}]}])
def test_malformed_provider_responses_are_safe(body, monkeypatch):
    async def response(_client, *_args, **_kwargs):
        return httpx.Response(200, json=body)
    monkeypatch.setattr(httpx.AsyncClient, 'request', response)
    provider = OpenRouterProvider(Settings(openrouter_api_key='SECRET_TEST_KEY'))
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.complete(provider.settings.premium_model, [], purpose='test'))
    assert error.value.code == 'provider_malformed'
    assert 'SECRET_TEST_KEY' not in str(error.value)
