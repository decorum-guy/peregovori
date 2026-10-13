import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.qwen import ready_identity
from test_sessions import make_test_app, options, create, assert_no_private_json


@pytest.mark.parametrize('payload', [
    {'status': 'ready', 'ready': False, 'adapter_loaded': True},
    {'status': 'ready', 'model': 'qwen3-8b-lora'},
    {'status': 'ready', 'ready': True, 'adapter_loaded': False},
    {'status': 'loading', 'ready': True, 'adapter_loaded': True},
    {'status': 'ready', 'ready': True, 'adapter_loaded': True}, [], None,
])
def test_health_does_not_guess_readiness_from_process_or_model_name(payload):
    assert ready_identity(payload) == {}


def test_qwen_reconnects_and_reports_actual_base_without_restart(tmp_path, monkeypatch):
    available = False

    async def health(_client, url, **kwargs):
        assert url == 'http://127.0.0.1:18080/health'
        return httpx.Response(200, json={'status': 'ready' if available else 'loading', 'ready': available,
                                        'adapter_loaded': available, 'base_model': 'Qwen/Qwen3-14B', 'model': 'qwen3-custom'})

    monkeypatch.setattr(httpx.AsyncClient, 'get', health)
    app, _ = make_test_app(tmp_path, lora_base_url='http://127.0.0.1:18080')
    with TestClient(app) as client:
        assert not client.get('/api/config?refresh=true').json()['engines'][1]['enabled']
        available = True
        ready = client.get('/api/config?refresh=true').json()['engines'][1]
        assert ready['enabled'] and ready['label'] == 'Qwen3-14B · Дообученная'
        available = False
        assert not client.get('/api/config?refresh=true').json()['engines'][1]['enabled']


def test_qwen_dialogue_keeps_selected_checkpoint_and_never_falls_back(tmp_path, monkeypatch):
    identity = {'status': 'ready', 'ready': True, 'adapter_loaded': True, 'base_model': 'Qwen/Qwen3-8B',
                'model': 'experiment-e2', 'adapter_fingerprint': 'a' * 64}
    lora_requests, clients = [], []
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        clients.append(kwargs)
        return real_client(*args, **kwargs)

    async def health(_client, _url, **_kwargs):
        return httpx.Response(200, json=identity)

    async def complete(_client, url, **kwargs):
        assert url.endswith('/v1/chat/completions')
        lora_requests.append(kwargs['json'])
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Я готов обсудить конкретные сроки и объём.'}}]})

    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy-secret:SECRET@example.invalid')
    monkeypatch.setattr(httpx.AsyncClient, 'get', health)
    monkeypatch.setattr(httpx.AsyncClient, 'post', complete)
    monkeypatch.setattr('app.service.httpx.AsyncClient', client_factory)
    app, provider = make_test_app(tmp_path, lora_base_url='http://127.0.0.1:18080', openrouter_proxy_url='http://127.0.0.1:10809')
    with TestClient(app) as client:
        session = create(client, options(engine_id='lora'))
        assert session['engine']['model_id'] == 'experiment-e2'
        assert session['engine']['label'] == 'Qwen3-8B · Дообученная'
        base = '/api/sessions/' + session['id']
        sent = client.post(base + '/message', json={'request_id': str(uuid.uuid4()), 'text': 'Какой срок реалистичен?'})
        assert sent.status_code == 200
        assert_no_private_json(sent.json())
        assert lora_requests[0]['model'] == 'experiment-e2'
        assert lora_requests[0]['messages'][0]['role'] == 'system'
        assert lora_requests[0]['messages'][-1]['content'] == 'Какой срок реалистичен?'
        identity['adapter_fingerprint'] = 'b' * 64
        changed = client.post(base + '/message', json={'request_id': str(uuid.uuid4()), 'text': 'Продолжим?'})
        assert changed.status_code == 502 and changed.json()['code'] == 'lora_model_changed'
        identity['ready'] = False
        offline = client.post(base + '/message', json={'request_id': client.get(base).json()['messages'][-1]['request_id'], 'text': 'Продолжим?'})
        assert offline.status_code == 502 and offline.json()['code'] == 'lora_unavailable'
        assert len(lora_requests) == 1
        assert [call['purpose'] for call in provider.calls] == ['case']
        client.post(base + '/finish')
        assert [call['purpose'] for call in provider.calls] == ['case']
        reviewed = client.post(base + '/debrief')
        assert reviewed.status_code == 200
        assert [call['purpose'] for call in provider.calls] == ['case', 'judge']
    assert all(kwargs.get('trust_env') is False and 'proxy' not in kwargs for kwargs in clients)
