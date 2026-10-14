"""Selective decoding contract and resume without any paid API call."""
import asyncio
import hashlib
import json
import sqlite3
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.prompts import ROLEPLAY_RULES
from app.providers import OpenRouterProvider
from app.usage import UsageLedger
from test_generator_recovery_usage import app_with_http, options, response
from app.providers import _mock_case
from test_sessions import with_sentinels


@pytest.fixture(autouse=True)
def preserve_main_event_loop():
    # asyncio.run closes its own loop and clears the main-thread default on Python 3.9.
    # Keep these contract tests from changing unrelated inference tests' loop state.
    previous = asyncio.get_event_loop()
    try:
        yield
    finally:
        asyncio.set_event_loop(previous)


@pytest.mark.parametrize('purpose,model,budget,expected', [
    ('roleplayer','anthropic/claude-opus-5.5',1200,{'effort':'low'}),
    ('case','anthropic/claude-opus-5.5',4096,None),
    ('judge','anthropic/claude-opus-5.5',2500,None),
    ('diagnostic','anthropic/claude-opus-5.5',256,None),
    ('roleplayer','openai/gpt-6-astra',1200,None),
    ('roleplayer','anthropic/claude-sonnet-4',1200,None),
])
def test_reasoning_payload_is_selective(purpose, model, budget, expected, monkeypatch):
    sent=[]
    async def request(_client,*args,**kwargs):
        sent.append(kwargs['json']);return httpx.Response(200,json=response('Complete spoken reply.'))
    monkeypatch.setattr(httpx.AsyncClient,'request',request)
    settings=Settings(openrouter_api_key='FAKE_TEST_SECRET',cloud_roleplayer_max_tokens=1200,cloud_roleplayer_reasoning_effort='low')
    reply=asyncio.run(OpenRouterProvider(settings).complete(model,[{'role':'user','content':'FAKE_PRIVATE_SENTINEL'}],purpose=purpose,max_tokens=budget))
    assert reply=='Complete spoken reply.'
    assert sent[0]['max_tokens']==budget
    assert sent[0].get('reasoning')==expected
    if expected: assert set(sent[0]['reasoning'])=={'effort'}


@pytest.mark.parametrize('effort', ['low','medium','high','default'])
def test_configurable_effort_and_omit_default(effort,monkeypatch):
    sent=[]
    async def request(_client,*args,**kwargs):
        sent.append(kwargs['json']);return httpx.Response(200,json=response('Reply.'))
    monkeypatch.setattr(httpx.AsyncClient,'request',request)
    settings=Settings(openrouter_api_key='FAKE_TEST_SECRET',cloud_roleplayer_reasoning_effort=effort)
    asyncio.run(OpenRouterProvider(settings).complete(settings.premium_model,[],purpose='roleplayer',max_tokens=1600))
    assert sent[0].get('reasoning')==({'effort':effort} if effort!='default' else None)


@pytest.mark.parametrize('budget',[599,4097,True,'1200'])
def test_invalid_output_budget_rejected(budget):
    with pytest.raises(ValueError,match='CLOUD_ROLEPLAYER_MAX_TOKENS'):
        Settings(cloud_roleplayer_max_tokens=budget).validate()


@pytest.mark.parametrize('effort',['none','minimal','SECRET_SENTINEL','enabled:false'])
def test_invalid_effort_rejected_without_echo(effort):
    with pytest.raises(ValueError) as error:Settings(cloud_roleplayer_reasoning_effort=effort).validate()
    assert effort not in str(error.value)


def test_env_configuration(monkeypatch):
    monkeypatch.setenv('CLOUD_ROLEPLAYER_MAX_TOKENS','1600');monkeypatch.setenv('CLOUD_ROLEPLAYER_REASONING_EFFORT','MEDIUM')
    s=Settings.from_env();s.validate()
    assert s.cloud_roleplayer_max_tokens==1600 and s.cloud_roleplayer_reasoning_effort=='medium'
    monkeypatch.setenv('CLOUD_ROLEPLAYER_MAX_TOKENS','SECRET_SENTINEL')
    with pytest.raises(ValueError) as error:Settings.from_env()
    assert 'SECRET_SENTINEL' not in str(error.value)


def test_resume_saved_turn_uses_new_budget_same_request_and_idempotency(tmp_path,monkeypatch):
    case=json.dumps(with_sentinels(_mock_case(options())))
    app,calls=app_with_http(tmp_path,monkeypatch,[response(case),response(None,'length'),response('Full spoken reply.')])
    original=replace(app.state.demo_service.settings,cloud_roleplayer_max_tokens=600,cloud_roleplayer_reasoning_effort='default')
    old=create_app(settings=original)
    with TestClient(old) as client:
        session=client.post('/api/sessions',json=options()).json();base='/api/sessions/'+session['id']
        turn={'text':'A saved human move.','request_id':'same-request-sentinel'}
        assert client.post(base+'/message',json=turn).json()['code']=='provider_truncated'
    updated=create_app(settings=replace(original,cloud_roleplayer_max_tokens=1200,cloud_roleplayer_reasoning_effort='low'))
    with TestClient(updated) as client:
        result=client.post(base+'/message',json=turn)
        assert result.status_code==200,result.text
        assert client.post(base+'/message',json=turn).status_code==200
        assert len([m for m in result.json()['messages'] if m['speaker']=='player'])==1
    assert len(calls)==3  # One case, old failing turn, one conscious retry; no auto/redundant call.
    assert calls[0]['max_tokens']==4096 and 'reasoning' not in calls[0]
    assert calls[1]['max_tokens']==600 and 'reasoning' not in calls[1]
    assert calls[2]['max_tokens']==1200 and calls[2]['reasoning']=={'effort':'low'}
    assert calls[1]['messages']==calls[2]['messages']
    rows=updated.state.provider.usage_ledger.rows([session['id']])
    assert rows[1]['reasoning_effort'] is None and rows[1]['retry_index']==0
    assert rows[2]['reasoning_effort']=='low' and rows[2]['retry_index']==1
    assert 'sentinel' not in json.dumps(rows)
    assert hashlib.sha256(ROLEPLAY_RULES.encode()).hexdigest()=='fe9f37b3d0d1c2989dd38971a194398f88b3e0b96bdf6aef926f7d76555a5656'
