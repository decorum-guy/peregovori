#!/usr/bin/env python3
"""Generate long RU sample PDFs via the real endpoint and a local MockProvider."""
import argparse
import os
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='docs/issue12_qa')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = (root / args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='peregovori-pdf-qa-') as temp:
    os.environ['LLM_MODE'] = 'mock'
    os.environ['DATABASE_PATH'] = str(Path(temp) / 'import.sqlite3')
    os.environ['DEMO_ACCESS_CODE'] = ''
    sys.path.insert(0, str(root / 'web' / 'backend'))
    from app.config import Settings
    from app.main import create_app
    from app.providers import MockProvider
    from fastapi.testclient import TestClient
    from pypdf import PdfReader
    provider = MockProvider()
    app = create_app(Settings(llm_mode='mock', database_path=str(Path(temp) / 'sessions.sqlite3')), provider=provider)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json={'scenario': 'conflict_then_negotiation', 'difficulty': 'medium',
                             'sphere': 'work', 'conflict_type': 'personal', 'student_side': 'protect', 'engine_id': 'premium', 'player_name': 'Аня'}).json()
        sid = session['id']
        store = app.state.session_store
        for i in range(18):
            store.reserve_message(sid, f'long-sample-{i}', f'Реплика {i+1}. ' +
                ('Обсудим условия проекта и уважение к личным границам. «Согласованный шаг» — проверяемый результат.\n' * 20) + ('ДЛИННОЕСЛОВО' * 40))
            store.complete_message(sid, f'long-sample-{i}', f'Ответ {i+1}. ' + ('Могу согласиться на проверяемый следующий шаг.\n' * 10))
        client.post(f'/api/sessions/{sid}/finish')
        before = len(provider.calls)
        response = client.get(f'/api/sessions/{sid}/export.pdf')
        assert response.status_code == 200 and len(provider.calls) == before
        (output / 'long-without-review.pdf').write_bytes(response.content)
        assert client.post(f'/api/sessions/{sid}/debrief').status_code == 200
        before = len(provider.calls)
        response = client.get(f'/api/sessions/{sid}/export.pdf')
        assert response.status_code == 200 and len(provider.calls) == before
        (output / 'long-review.pdf').write_bytes(response.content)
        for name in ('long-without-review.pdf', 'long-review.pdf'):
            reader = PdfReader(str(output / name))
            assert len(reader.pages) > 20
            print(f'{name}: {len(reader.pages)} pages, export model calls: 0')
