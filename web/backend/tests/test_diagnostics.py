"""The full smoke command must never recover another running app's SQLite."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from test_sessions import make_test_app, create


def test_game_diagnostic_does_not_touch_pending_messages_in_live_database(tmp_path):
    app, _ = make_test_app(tmp_path)
    with TestClient(app) as client:
        session = create(client)
    app.state.session_store.reserve_message(session['id'], str(uuid.uuid4()), 'Реплика ещё обрабатывается.')
    root = Path(__file__).resolve().parents[3]
    env = dict(os.environ, DATABASE_PATH=app.state.session_store.database_path,
               OPENROUTER_API_KEY='dummy-diagnostic-test-key', LLM_MODE='openrouter', LORA_BASE_URL='',
               PREMIUM_MODEL='anthropic/claude-opus-5.5', CASE_MODEL='anthropic/claude-opus-5.5', JUDGE_MODEL='anthropic/claude-opus-5.5',
               DEMO_ACCESS_CODE='', COMPLETION_ENABLED='false')
    # A separate interpreter exercises the import-time app, with a deterministic
    # network double. The same paid/game CLI path runs without any external call.
    code = '''
import asyncio, sys
from argparse import Namespace
sys.path.insert(0, 'web/backend')
sys.path.insert(0, 'scripts')
import app.providers
class DiagnosticProvider(app.providers.MockProvider):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
    async def model_ids(self):
        return {self.settings.premium_model, self.settings.case_model, self.settings.judge_model}
    async def complete(self, model, messages, **kwargs):
        if kwargs['purpose'] == 'diagnostic': return 'Тестовое соединение.'
        return await super().complete(model, messages, **kwargs)
app.providers.OpenRouterProvider = DiagnosticProvider
import test_openrouter
raise SystemExit(asyncio.run(test_openrouter.run(Namespace(direct=True, game=True, judge=True, engine='premium'))))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=root, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert app.state.session_store.get(session['id'])['messages'][-1]['delivery_status'] == 'pending'
