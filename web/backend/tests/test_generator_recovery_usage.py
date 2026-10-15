"""Regression of observed live failures, entirely offline HTTP doubles."""
import asyncio
import hashlib
import json
import sqlite3
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import RuntimeCase
from app.prompts import generator_prompt, ROLEPLAY_RULES
from app.providers import OpenRouterProvider, ProviderError, _mock_case, _extract_options
from app.usage import UsageLedger, usage_scope
from test_sessions import with_sentinels, assert_no_private_json


MODEL = 'anthropic/claude-opus-5.5'


def options(language='ru'):
    return dict(language=language, scenario='conflict_only', difficulty='hard', sphere='family',
                conflict_type='personal', student_side='protect', engine_id='premium')


def response(content, finish='stop', usage=None):
    return dict(model=MODEL, choices=[dict(finish_reason=finish, message=dict(content=content,
                reasoning='REASONING_SECRET_SENTINEL'))], usage=usage if usage is not None else
                dict(prompt_tokens=100, completion_tokens=70, total_tokens=170, cost=0.01,
                     completion_tokens_details=dict(reasoning_tokens=20)),
                untrusted='RAW_RESPONSE_SECRET_SENTINEL')


def app_with_http(tmp_path, monkeypatch, bodies):
    requests = []
    async def request(_client, method, url, **kwargs):
        assert method == 'POST'
        requests.append(kwargs['json'])
        return httpx.Response(200, json=bodies.pop(0))
    monkeypatch.setattr(httpx.AsyncClient, 'request', request)
    settings = Settings(database_path=str(tmp_path / 'sessions.sqlite3'), openrouter_api_key='API_SECRET_SENTINEL',
                        openrouter_proxy_url='http://user:PROXY_SECRET_SENTINEL@example.invalid:8080',
                        completion_enabled=False)  # Isolate scripted 1:1 request/retry and accounting tests.
    return create_app(settings=settings), requests


@pytest.mark.parametrize('language', ['ru', 'en'])
@pytest.mark.parametrize('closed_json', [False, True])
def test_length_finish_is_rejected_even_for_parseable_json_and_repaired_once(tmp_path, monkeypatch, language, closed_json):
    case = with_sentinels(_mock_case(options(language)))
    text = json.dumps(case, ensure_ascii=False)
    app, calls = app_with_http(tmp_path, monkeypatch, [response(text if closed_json else text[:-30], 'length'), response(text)])
    with TestClient(app) as client:
        result = client.post('/api/sessions', json=options(language))
    assert result.status_code == 200, result.text
    assert result.json()['source'] == 'openrouter'
    assert result.json()['settings']['language'] == language
    assert app.state.session_store.get(result.json()['id'])['runtime_case']['category'] == 'MODEL_MANIPULATOR'
    assert_no_private_json(result.json())
    assert len(calls) == 2 and all(call['max_tokens'] == 4096 for call in calls)
    assert 'shorter COMPLETE JSON' in calls[1]['messages'][-1]['content']
    rows = app.state.provider.usage_ledger.rows()
    assert [row['retry_index'] for row in rows] == [0, 1]
    assert [row['outcome'] for row in rows] == ['truncated', 'complete']
    assert [row['finish_reason'] for row in rows] == ['length', 'stop']
    assert all(row['category'] == 'Generator' and row['reasoning_tokens'] == 20 and row['visible_output_tokens'] == 50 for row in rows)
    assert all(row['actual_model'] == MODEL and row['cost_usd'] == .01 for row in rows)
    assert all('SECRET_SENTINEL' not in json.dumps(row) for row in rows)


@pytest.mark.parametrize('language', ['ru', 'en'])
def test_long_decoding_is_strictly_rejected_and_regenerated_not_silently_cut(tmp_path, monkeypatch, language):
    valid = with_sentinels(_mock_case(options(language)))
    invalid = json.loads(json.dumps(valid))
    invalid['teaching']['decoding'] = 'PRIVATE_DECODING_SENTINEL ' * 20
    with pytest.raises(ValueError):
        RuntimeCase.model_validate(invalid)
    app, calls = app_with_http(tmp_path, monkeypatch, [response(json.dumps(invalid)), response(json.dumps(valid))])
    with TestClient(app) as client:
        result = client.post('/api/sessions', json=options(language))
    assert result.status_code == 200, result.text
    assert_no_private_json(result.json())
    assert len(calls) == 2
    repair = calls[1]['messages'][-1]['content']
    assert 'teaching.decoding: string_too_long (max_length=300)' in repair
    assert 'PRIVATE_DECODING_SENTINEL' not in repair
    saved = app.state.session_store.get(result.json()['id'])['runtime_case']
    assert saved['teaching']['decoding'] == valid['teaching']['decoding']
    assert saved['opponent'] == valid['opponent']


def test_two_invalid_responses_stop_without_third_request_or_private_error(tmp_path, monkeypatch):
    case = _mock_case(options())
    case['teaching']['decoding'] = 'PRIVATE_DECODING_SENTINEL ' * 20
    app, calls = app_with_http(tmp_path, monkeypatch, [response('{"private":"SECRET', 'length'), response(json.dumps(case))])
    with TestClient(app) as client:
        result = client.post('/api/sessions', json=options())
    assert result.status_code == 502 and result.json()['code'] == 'invalid_generated_case'
    assert len(calls) == 2 and 'SENTINEL' not in result.text
    assert len(app.state.provider.usage_ledger.rows()) == 2


def test_schema_constraints_are_derived_and_cloud_a_stays_frozen():
    for language in ['ru', 'en']:
        prompt = generator_prompt(options(language))[-1]['content']
        assert '"maxLength":300' in prompt and '"maxItems":12' in prompt
        assert '"additionalProperties":false' in prompt
        assert '"title":{"' in prompt  # The public title property was not stripped.
    assert hashlib.sha256(ROLEPLAY_RULES.encode()).hexdigest() == 'fe9f37b3d0d1c2989dd38971a194398f88b3e0b96bdf6aef926f7d76555a5656'


def test_content_free_accounting_and_missing_cost_persist_on_restart(tmp_path, monkeypatch):
    case = json.dumps(with_sentinels(_mock_case(options())))
    judge = json.dumps(dict(summary='Короткий диалог.', strengths=[], risks=[], next_step='Уточнить смысл.', example_phrase=None))
    app, calls = app_with_http(tmp_path, monkeypatch, [response(case), response('Услышала вас.', usage={}), response(judge)])
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        base = '/api/sessions/' + session['id']
        turn = dict(text='USER_PRIVATE_SENTINEL', request_id='REQUEST_PRIVATE_SENTINEL')
        assert client.post(base + '/message', json=turn).status_code == 200
        assert client.post(base + '/message', json=turn).status_code == 200
        client.post(base + '/finish')
        assert len(calls) == 2  # No automatic Judge.
        assert client.post(base + '/debrief').status_code == 200
        assert client.post(base + '/debrief').status_code == 200
    rows = UsageLedger(app.state.session_store.database_path).rows([session['id']])
    assert [row['category'] for row in rows] == ['Generator', 'Roleplayer', 'Judge']
    assert all(row['retry_index'] == 0 for row in rows)
    assert rows[1]['cost_status'] == 'cost_not_reported' and rows[1]['cost_usd'] is None
    assert rows[1]['prompt_tokens'] is None and rows[1]['reasoning_tokens'] is None
    assert all(row['duration_seconds'] >= 0 for row in rows)
    assert 'SENTINEL' not in json.dumps(rows)
    assert all('messages' not in row and 'content' not in row for row in rows)


def test_explicit_player_retry_is_counted_across_restart_without_duplicating_turn(tmp_path, monkeypatch):
    case = json.dumps(with_sentinels(_mock_case(options())))
    app, calls = app_with_http(tmp_path, monkeypatch, [response(case), response(None, 'length'), response('Теперь ответ полный.')])
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        base = '/api/sessions/' + session['id']
        turn = dict(text='Нейтральная реплика.', request_id=str(uuid.uuid4()))
        assert client.post(base + '/message', json=turn).status_code == 502
    restarted = create_app(settings=app.state.demo_service.settings)
    with TestClient(restarted) as client:
        result = client.post(base + '/message', json=turn)
        assert result.status_code == 200, result.text
        assert len([m for m in result.json()['messages'] if m['speaker'] == 'player']) == 1
        client.post(base + '/finish')
        client.post(base + '/skip-debrief')
    rows = restarted.state.provider.usage_ledger.rows([session['id']])
    assert [r['retry_index'] for r in rows if r['category'] == 'Roleplayer'] == [0, 1]
    assert not any(r['category'] == 'Judge' for r in rows)
    assert len(calls) == 3


def test_provider_auth_error_is_not_automatically_retried(tmp_path, monkeypatch):
    calls = []
    async def failed(_client, *args, **kwargs):
        calls.append(1)
        return httpx.Response(401, json={'error': 'API_SECRET_SENTINEL'})
    monkeypatch.setattr(httpx.AsyncClient, 'request', failed)
    app = create_app(settings=Settings(openrouter_api_key='API_SECRET_SENTINEL', database_path=str(tmp_path / 'auth.sqlite3')))
    with TestClient(app) as client:
        result = client.post('/api/sessions', json=options())
    assert result.status_code == 502 and result.json()['code'] == 'provider_auth'
    assert len(calls) == 1
    row = app.state.provider.usage_ledger.rows()[0]
    assert row['cost_status'] == 'cost_not_reported' and 'SENTINEL' not in json.dumps(row)
