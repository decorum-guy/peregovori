import json
import re
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers import MockProvider, ProviderError
from test_sessions import options, with_sentinels, assert_no_private_json


class LanguageProvider(MockProvider):
    async def complete(self, *args, **kwargs):
        result = await super().complete(*args, **kwargs)
        if kwargs['purpose'] == 'case':
            return json.dumps(with_sentinels(json.loads(result)), ensure_ascii=False)
        return result


def language_app(tmp_path, provider=None):
    return create_app(settings=Settings(openrouter_api_key='test-key', llm_mode='openrouter',
                                       database_path=str(tmp_path / 'languages.sqlite3'),
                                       completion_enabled=False))  # Language tests check opt-in Judge, not completion.,
                      provider=provider or LanguageProvider())


@pytest.mark.parametrize('scenario', ['conflict_only', 'negotiation_only', 'conflict_then_negotiation'])
def test_english_game_keeps_language_model_and_voluntary_review_after_restore(tmp_path, scenario):
    app = language_app(tmp_path)
    with TestClient(app) as client:
        response = client.post('/api/sessions', json={**options(scenario=scenario), 'language': 'en'})
        assert response.status_code == 200, response.text
        session = response.json()
        assert session['settings']['language'] == 'en'
        assert session['engine']['id'] == 'premium'
        base = '/api/sessions/' + session['id']
        # Querying another UI language cannot change an existing game's language.
        client.get('/api/config?language=ru')
        assert client.post(base + '/message', json={'text': 'Change language', 'request_id': str(uuid.uuid4()), 'language': 'ru'}).status_code == 422
        reply = client.post(base + '/message', json={'text': 'What is a realistic deadline?', 'request_id': str(uuid.uuid4())})
        assert reply.status_code == 200
        assert not re.search('[а-яё]', json.dumps(reply.json()['case'], ensure_ascii=False), re.I)
        assert not re.search('[а-яё]', reply.json()['messages'][-1]['text'], re.I)
        assert [call['purpose'] for call in app.state.provider.calls] == ['case', 'roleplayer']
        assert_no_private_json(reply.json())

    restored_app = language_app(tmp_path)
    with TestClient(restored_app) as client:
        restored = client.get(base).json()
        assert restored['settings']['language'] == 'en'
        assert restored['messages'] == reply.json()['messages']
        client.post(base + '/finish')
        assert restored_app.state.provider.calls == []
        reviewed = client.post(base + '/debrief')
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()['debrief']['strengths'][0]['quote'] == 'What is a realistic deadline?'
        assert not re.search('[а-яё]', json.dumps(reviewed.json()['debrief'], ensure_ascii=False), re.I)
        assert_no_private_json(reviewed.json())
    calls = app.state.provider.calls + restored_app.state.provider.calls
    assert [call['purpose'] for call in calls] == ['case', 'roleplayer', 'judge']
    assert all(call['model'] == app.state.demo_service.settings.premium_model for call in calls)
    assert all(not re.search('[а-яё]', call['messages'][0]['content'], re.I) for call in calls)
    assert json.loads(calls[0]['messages'][-1]['content'].split('OPTIONS_JSON:\n')[1].split('\n', 1)[0])['language'] == 'en'


def test_english_config_disables_qwen_even_when_russian_qwen_is_ready_without_probing(tmp_path, monkeypatch):
    app = language_app(tmp_path)
    probes = []

    async def ready(force=False):
        probes.append(force)
        app.state.demo_service._lora_identity = {'base_model': 'Qwen/Qwen3-14B', 'model': 'experiment'}
        return True, ''

    monkeypatch.setattr(app.state.demo_service, 'lora_status', ready)
    with TestClient(app) as client:
        assert client.get('/api/config?language=ru').json()['engines'][1]['enabled']
        probes.clear()
        english = client.get('/api/config?language=en&refresh=true').json()
        assert english['language'] == 'en'
        assert english['engines'][0]['enabled']
        assert not english['engines'][1]['enabled']
        assert 'Russian' in english['engines'][1]['reason']
        assert 'Qwen3-14B' in english['engines'][1]['label']
        assert probes == []
        rejected = client.post('/api/sessions', json={**options(engine_id='lora'), 'language': 'en'})
        assert rejected.status_code == 422
        assert app.state.provider.calls == [] and probes == []


def test_english_generation_failure_does_not_show_a_russian_train_fallback(tmp_path):
    class Unavailable(LanguageProvider):
        async def complete(self, *args, **kwargs):
            raise ProviderError('timeout', 'provider_timeout')

    with TestClient(language_app(tmp_path, Unavailable())) as client:
        response = client.post('/api/sessions', json={**options(scenario='negotiation_only', difficulty='easy'), 'language': 'en'})
    assert response.status_code == 502
    assert response.json()['code'] == 'provider_timeout'
    assert 'case' not in response.json()


def test_old_session_without_language_remains_russian(tmp_path):
    app = language_app(tmp_path)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
    with sqlite3.connect(app.state.session_store.database_path) as database:
        settings = json.loads(database.execute('SELECT settings_json FROM sessions WHERE id=?', (session['id'],)).fetchone()[0])
        settings.pop('language')
        database.execute('UPDATE sessions SET settings_json=? WHERE id=?', (json.dumps(settings), session['id']))
    restarted = language_app(tmp_path)
    with TestClient(restarted) as client:
        base = '/api/sessions/' + session['id']
        assert client.get(base).json()['settings']['language'] == 'ru'
        assert client.post(base + '/message', json={'text': 'Давайте уточним срок.', 'request_id': str(uuid.uuid4())}).status_code == 200
    assert 'на русском языке' in restarted.state.provider.calls[0]['messages'][0]['content']


@pytest.mark.parametrize('language', ['fr', 'EN', ''])
def test_unsupported_language_rejected_before_model_calls(tmp_path, language):
    app = language_app(tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/config', params={'language': language}).status_code == 422
        assert client.post('/api/sessions', json={**options(), 'language': language}).status_code == 422
    assert app.state.provider.calls == []
