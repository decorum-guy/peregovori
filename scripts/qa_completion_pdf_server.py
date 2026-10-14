#!/usr/bin/env python3
"""Disposable offline UI fixture server. NEVER uses OpenRouter or a live Qwen."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--access-code', default='')
parser.add_argument('--port', type=int, default=8777)
parser.add_argument('--database', default='/private/tmp/peregovori-completion-qa.sqlite3')
args = parser.parse_args()
# Isolate even app.main's import-time app from the real session store and gate.
os.environ['LLM_MODE'] = 'mock'
os.environ['DATABASE_PATH'] = args.database
os.environ['DEMO_ACCESS_CODE'] = ''
sys.path.insert(0, str(ROOT / 'web' / 'backend'))
from app.config import Settings
from app.main import create_app
from app.providers import MockProvider
import uvicorn


class FixtureProvider(MockProvider):
    async def complete(self, model, messages, *, purpose, **kwargs):
        if purpose == 'completion':
            self.calls.append({'purpose': purpose, 'model': model})
            last = json.loads(messages[-1]['content'])['transcript'][-1]
            return json.dumps({'status': 'achieved', 'confidence': 0.99, 'all_goals_met': True,
                               'unresolved': [], 'evidence': [{'message_id': last['id'], 'quote': last['text']}]})
        return await super().complete(model, messages, purpose=purpose, **kwargs)


provider = FixtureProvider()
app = create_app(Settings(llm_mode='mock', database_path=args.database, demo_access_code=args.access_code), provider=provider)


@app.get('/_qa/calls')
def qa_calls():
    return [call['purpose'] for call in provider.calls]


# Put the QA-only route ahead of the production SPA fallback.
app.router.routes.insert(0, app.router.routes.pop())

uvicorn.run(app, host='127.0.0.1', port=args.port)
