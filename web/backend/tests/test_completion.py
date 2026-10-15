"""Offline classifier-contract checks; these do not measure a live model's accuracy."""
import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.completion import CompletionResult, confirmed_achievement
from app.storage import SessionStore
from app.providers import MockProvider
from app.usage import UsageLedger, usage_scope
from test_sessions import FakeProvider, make_test_app, options, SENTINELS


@pytest.fixture(autouse=True)
def preserve_event_loop():
    # asyncio.run clears the main-thread loop on Python 3.9. Existing inference
    # tests construct locks synchronously; leave their loop policy untouched.
    try:
        previous = asyncio.get_event_loop()
    except RuntimeError:
        previous = None
    yield
    asyncio.set_event_loop(previous)


CONFIRMATION = 'Признаю ваше право отказать без оценки вашей лояльности. Отзываю требование.'


class CompletionProvider(FakeProvider):
    classification = 'achieved'
    completion_reply = CONFIRMATION
    detector_failure = False
    detector_started = None
    detector_release = None
    malicious_evidence = False
    judge_failure = False

    async def complete(self, model, messages, *, purpose, **kwargs):
        if purpose != 'completion':
            if purpose == 'judge' and self.judge_failure:
                raise RuntimeError('offline failure')
            if purpose == 'roleplayer':
                self.roleplay_reply = self.completion_reply
            if purpose == 'judge' and messages[0]['content'].startswith('You are'):
                self.calls.append({'model': model, 'messages': messages, 'purpose': purpose})
                return await MockProvider().complete(model, messages, purpose=purpose, **kwargs)
            return await super().complete(model, messages, purpose=purpose, **kwargs)
        self.calls.append({'model': model, 'messages': messages, 'purpose': purpose})
        if self.detector_started:
            self.detector_started.set()
        if self.detector_release:
            await self.detector_release.wait()
        if self.detector_failure:
            raise RuntimeError('offline detector failure')
        last = json.loads(messages[-1]['content'])['transcript'][-1]
        return json.dumps({'status': self.classification, 'confidence': 0.99,
                           'all_goals_met': self.classification == 'achieved', 'unresolved': [],
                           'evidence': [{'message_id': last['id'], 'quote': 'invented quote that does not exist' if self.malicious_evidence else last['text']}]}, ensure_ascii=False)


def three_turns(client, session_id):
    result = None
    for i in range(3):
        result = client.post(f'/api/sessions/{session_id}/message', json={'request_id': f'completion-turn-{i}', 'text': 'Обсудим право на отказ и конкретные условия.'})
        assert result.status_code == 200
    return result.json()


def checks(provider):
    return [c for c in provider.calls if c['purpose'] == 'completion']


@pytest.mark.parametrize('classification,difficulty,expected', [
    ('achieved', 'medium', True), ('partial', 'medium', False),
    ('not_achieved', 'medium', False), ('uncertain', 'medium', False), ('achieved', 'impossible', False),
])
def test_classes_public_context_and_no_judge(tmp_path, classification, difficulty, expected):
    provider = CompletionProvider()
    provider.classification = classification
    provider.completion_reply = {'achieved': CONFIRMATION,
        'partial': 'Буду говорить спокойнее, но всё равно требую принять всю работу.',
        'not_achieved': 'Ладно, согласен. Но сначала вы обязаны выполнить прежнее требование.',
        'uncertain': 'Возможно, обсудим это когда-нибудь.'}[classification]
    app, _ = make_test_app(tmp_path, provider, completion_model='openai/gpt-6.1-sol', completion_min_turns=3)
    with TestClient(app) as client:
        created = client.post('/api/sessions', json=options(difficulty=difficulty)).json()
        final = three_turns(client, created['id'])
        assert bool(final['completion_hint']) == expected
        assert final['status'] == 'active' and final['debrief'] is None
        assert len(checks(provider)) == 1
        call = checks(provider)[0]
        assert call['model'] == 'openai/gpt-6.1-sol'
        payload = json.loads(call['messages'][-1]['content'])
        assert payload['case'] == created['case']
        assert payload['difficulty'] == difficulty
        assert len(payload['transcript']) == 7
        assert all(secret not in json.dumps(call) for secret in SENTINELS)
        assert not any(c['purpose'] == 'judge' for c in provider.calls)
        duplicate = client.post(f"/api/sessions/{created['id']}/message", json={'request_id': 'completion-turn-2', 'text': 'Обсудим право на отказ и конкретные условия.'}).json()
        assert duplicate['completion_hint'] == final['completion_hint']
        assert len(checks(provider)) == 1



@pytest.mark.parametrize('classify,expected', [('achieved', True), ('partial', False)])
def test_first_successful_reply_is_eligible_for_immediate_completion_hint(tmp_path, classify, expected):
    """One exchange is enough to detect explicit success; it does not force success."""
    provider = CompletionProvider()
    provider.classification = classify
    provider.completion_reply = (
        'Я больше не буду тебя так называть; буду обращаться по имени.'
        if expected else 'Я поняла, но всё равно продолжу называть тебя так.'
    )
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        result = client.post(
            f"/api/sessions/{session['id']}/message",
            json={'request_id': 'first-boundary-reply', 'text': 'Пожалуйста, обращайся по имени.'},
        )
        assert result.status_code == 200
        snapshot = result.json()
        assert snapshot['status'] == 'active'
        assert bool(snapshot['completion_hint']) is expected
        assert len(checks(provider)) == 1
        assert not any(c['purpose'] == 'judge' for c in provider.calls)
        if expected:
            assert snapshot['completion_hint']['status'] == 'offered'
            assert client.get(f"/api/sessions/{session['id']}").json()['completion_hint'] == snapshot['completion_hint']


def test_public_completion_policy_no_longer_requires_three_turns():
    from app.config import Settings
    s = Settings()
    assert s.completion_min_turns == 1
    s.validate()




def test_goal_achieved_on_second_reply_bypasses_periodic_cooldown(tmp_path):
    provider = CompletionProvider()
    provider.classification = 'partial'
    provider.completion_reply = 'Я пока хочу оставить прозвище, хотя понимаю, что тебе неприятно.'
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        url = f"/api/sessions/{session['id']}/message"
        first = client.post(url, json={'request_id': 'disagreement-1', 'text': 'Прошу использовать моё имя.'})
        assert first.status_code == 200
        assert first.json()['completion_hint'] is None
        assert len(checks(provider)) == 1
        provider.classification = 'achieved'
        provider.completion_reply = 'Хорошо, больше не буду использовать прозвище, буду обращаться по имени.'
        second = client.post(url, json={'request_id': 'agreement-2', 'text': 'Это важно для меня.'})
        assert second.status_code == 200
        assert second.json()['completion_hint']['status'] == 'offered'
        assert len(checks(provider)) == 2
        assert not any(c['purpose'] == 'judge' for c in provider.calls)


@pytest.mark.parametrize('reply,expected', [
    ('Больше не буду обращаться так; договорились.', True),
    ("I agree. I will not use that name again.", True),
    ('Давай сначала поговорим об этом.', True),
    ('Я тебя услышала, но ничего не обещаю.', False),
])
def test_cheap_candidate_only_prioritizes_a_semantic_check(reply, expected):
    from app.completion import potential_concession
    assert potential_concession(reply) is expected



def test_decline_restore_draft_independence_and_no_repeat(tmp_path):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider, completion_min_turns=3)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        final = three_turns(client, session['id'])
        hint = final['completion_hint']
        assert client.get(f"/api/sessions/{session['id']}").json()['completion_hint'] == hint
        response = client.post(f"/api/sessions/{session['id']}/completion-hint/dismiss", json={'reply_id': hint['reply_id']})
        assert response.json()['completion_hint']['status'] == 'dismissed'
        assert response.json()['messages'] == final['messages']
        assert SessionStore(app.state.session_store.database_path).get(session['id'])['completion_hint']['status'] == 'dismissed'
        for i in range(3, 10):
            assert client.post(f"/api/sessions/{session['id']}/message", json={'request_id': f'completion-turn-{i}', 'text': 'Продолжим.'}).status_code == 200
        assert len(checks(provider)) == 1
        assert client.post(f"/api/sessions/{session['id']}/finish").json()['debrief_status'] == 'not_requested'
        assert not any(c['purpose'] == 'judge' for c in provider.calls)
        assert client.post(f"/api/sessions/{session['id']}/debrief").status_code == 200
        assert sum(c['purpose'] == 'judge' for c in provider.calls) == 1


@pytest.mark.parametrize('mode', ['failure', 'bad_evidence', 'disabled', 'context_cap'])
def test_abstention_and_request_budgets(tmp_path, mode):
    provider = CompletionProvider()
    provider.detector_failure = mode == 'failure'
    provider.malicious_evidence = mode == 'bad_evidence'
    settings = {'completion_enabled': mode != 'disabled', 'completion_max_checks': 2}
    if mode == 'context_cap':
        settings['completion_max_input_chars'] = 1000
    app, _ = make_test_app(tmp_path, provider, completion_min_turns=3, **settings)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        for i in range(12):
            result = client.post(f"/api/sessions/{session['id']}/message", json={'request_id': f'budget-turn-{i}', 'text': 'Обсудим детали.'})
            assert result.status_code == 200 and result.json()['completion_hint'] is None
        assert len(checks(provider)) == (0 if mode in ('disabled', 'context_cap') else 2)
        assert len(result.json()['messages']) == 25


def test_qwen_never_checks_paid_provider(tmp_path):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider, completion_min_turns=3)
    service = app.state.demo_service
    async def exercise():
        session = await service.create_session(__import__('app.models', fromlist=['SessionOptions']).SessionOptions(**options()))
        # Existing Qwen sessions reach the same post-delivery gate; no OpenRouter completion.
        with app.state.session_store._connection() as db:
            db.execute("UPDATE sessions SET engine_id = 'lora' WHERE id = ?", (session['id'],))
        await service._check_completion(session['id'], session['messages'][-1]['id'])
    asyncio.run(exercise())
    assert not checks(provider)


@pytest.mark.parametrize('race', ['finish', 'new_turn', 'duplicate'])
def test_detector_races(tmp_path, race):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider, completion_min_turns=3)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            session = (await client.post('/api/sessions', json=options())).json()
            url = f"/api/sessions/{session['id']}"
            for i in range(2):
                await client.post(url + '/message', json={'request_id': f'race-turn-{i}', 'text': 'Обсудим.'})
            provider.detector_started = asyncio.Event()
            provider.detector_release = asyncio.Event()
            task = asyncio.create_task(client.post(url + '/message', json={'request_id': 'race-turn-2', 'text': 'Уточним.'}))
            await provider.detector_started.wait()
            assert (await client.get(url)).json()['completion_hint'] is None
            if race == 'finish':
                await client.post(url + '/finish')
            elif race == 'new_turn':
                await client.post(url + '/message', json={'request_id': 'race-turn-3', 'text': 'Ещё вопрос.'})
            else:
                duplicate = await client.post(url + '/message', json={'request_id': 'race-turn-2', 'text': 'Уточним.'})
                assert duplicate.status_code == 200
            provider.detector_release.set()
            result = (await task).json()
            assert bool(result['completion_hint']) == (race == 'duplicate')
            assert len(checks(provider)) == 1
            assert not any(c['purpose'] == 'judge' for c in provider.calls)
    asyncio.run(exercise())


def test_failed_cancelled_turns_and_interrupted_reservation(tmp_path):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider, completion_min_turns=3)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        store = app.state.session_store
        sid = session['id']
        for i in range(3):
            store.reserve_message(sid, f'stored-turn-{i}', 'Диалог.')
            if i == 2:
                assert not store.reserve_completion(sid, f'stored-turn-{i}-reply', min_turns=3, cooldown=3, max_checks=4)
                store.fail_message(sid, f'stored-turn-{i}')
                assert not store.reserve_completion(sid, f'stored-turn-{i}-reply', min_turns=3, cooldown=3, max_checks=4)
                store.reserve_message(sid, f'stored-turn-{i}', 'Диалог.')
            store.complete_message(sid, f'stored-turn-{i}', CONFIRMATION)
        assert store.reserve_completion(sid, 'stored-turn-2-reply', min_turns=3, cooldown=3, max_checks=4)
        restarted = SessionStore(store.database_path)
        assert not restarted.reserve_completion(sid, 'stored-turn-2-reply', min_turns=3, cooldown=3, max_checks=4)
        restarted.complete_completion(sid, 'stored-turn-2-reply', True)
        assert restarted.get(sid)['completion_hint'] is None
        store.reserve_message(sid, 'cancelled-turn', 'Ещё вопрос.')
        store.finish(sid)
        store.complete_message(sid, 'cancelled-turn', CONFIRMATION)
        assert not store.reserve_completion(sid, 'cancelled-turn-reply', min_turns=3, cooldown=3, max_checks=4)


@pytest.mark.parametrize('changes', [ {'confidence': 0.94}, {'confidence': '0.99'}, {'confidence': float('nan')},
    {'all_goals_met': 'true'}, {'unresolved': ['условие']}, {'evidence': []}, {'extra': 'untrusted'}])
def test_strict_schema_rejects_unsupported_success(tmp_path, changes):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider, completion_min_turns=3)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        last = session['messages'][-1]
        data = {'status': 'achieved', 'confidence': 0.99, 'all_goals_met': True, 'unresolved': [],
                'evidence': [{'message_id': last['id'], 'quote': last['text']}]}
        data.update(changes)
        try:
            parsed = CompletionResult.model_validate(data)
        except ValidationError:
            return
        assert not confirmed_achievement(parsed, session)


def test_completion_usage_is_separate_from_judge(tmp_path):
    ledger = UsageLedger(str(tmp_path / 'usage.sqlite3'))
    with usage_scope('test-session', 'completion/reply', 'conflict_only'):
        ledger.record(purpose='completion', model='openai/gpt-6.1-sol', body={'usage': {'prompt_tokens': 200, 'completion_tokens': 40, 'cost': 0.001}}, seconds=1, outcome='complete', max_tokens=800, temperature=0)
    row = ledger.rows()[0]
    assert row['category'] == 'Completion' and row['cost_usd'] == 0.001


def test_completion_timeout_keeps_delivered_turn_and_consumes_attempt(tmp_path, monkeypatch):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider, completion_min_turns=3)
    async def timeout(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError()
    monkeypatch.setattr('app.service.asyncio.wait_for', timeout)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        final = three_turns(client, session['id'])
        assert final['completion_hint'] is None
        assert len(final['messages']) == 7
        assert final['messages'][-1]['delivery_status'] == 'sent'
        with app.state.session_store._connection() as db:
            assert db.execute('SELECT count(*) FROM completion_checks').fetchone()[0] == 1


def test_completion_config_rejects_luna_and_unsafe_budgets():
    from app.config import Settings
    for overrides in ({'completion_model': 'openai/gpt-6-luna'}, {'completion_min_turns': 0},
                      {'completion_max_checks': 11}, {'completion_max_tokens': 9000},
                      {'completion_timeout_seconds': float('nan')}, {'completion_model': 'qwen/local'}):
        with pytest.raises(ValueError):
            Settings(**overrides).validate()


def test_real_provider_completion_payload_and_usage_without_network(tmp_path, monkeypatch):
    from app.config import Settings
    from app.providers import OpenRouterProvider
    sent = []
    async def request(_client, *args, **kwargs):
        sent.append(kwargs['json'])
        return httpx.Response(200, json={'model': 'openai/gpt-6.1-sol', 'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}],
                                        'usage': {'prompt_tokens': 180, 'completion_tokens': 30, 'cost': 0.002}})
    monkeypatch.setattr(httpx.AsyncClient, 'request', request)
    provider = OpenRouterProvider(Settings(openrouter_api_key='FAKE_ONLY'))
    provider.usage_ledger = UsageLedger(str(tmp_path / 'payload.sqlite3'))
    with usage_scope('fake-session', 'completion/reply', 'conflict_only'):
        asyncio.run(provider.complete('openai/gpt-6.1-sol', [], purpose='completion', json_mode=True, max_tokens=800, temperature=0))
    assert sent[0]['reasoning'] == {'effort': 'low'}
    assert sent[0]['max_tokens'] == 800
    assert sent[0]['response_format'] == {'type': 'json_object'}
    assert 'temperature' not in sent[0]
    row = provider.usage_ledger.rows()[0]
    assert row['category'] == 'Completion' and row['cost_usd'] == 0.002
    assert row['session_id'] == 'fake-session' and row['reasoning_effort'] == 'low'
