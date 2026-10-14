import json
import re
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.pdf_export import export_filename
from test_completion import CompletionProvider, three_turns
from test_demo_guard import _headers
from test_sessions import make_test_app, options, SENTINELS


def read_pdf(response):
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert response.content.startswith(b'%PDF-')
    assert 'attachment; filename="line-of-decision-' in response.headers['content-disposition']
    reader = PdfReader(BytesIO(response.content))
    assert all(abs(float(p.mediabox.width) - 595.28) < 1 for p in reader.pages)
    return reader, '\n'.join(p.extract_text() for p in reader.pages)


@pytest.mark.parametrize('language', ['ru', 'en'])
@pytest.mark.parametrize('review', [True, False])
def test_public_full_pdf_review_opt_in_and_no_calls_on_export(tmp_path, language, review):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        values = dict(options(), language=language, player_name='Аня <b>& / ../../')
        session = client.post('/api/sessions', json=values).json()
        sid = session['id']
        transcript = three_turns(client, sid)
        client.post(f'/api/sessions/{sid}/finish')
        if review:
            final = client.post(f'/api/sessions/{sid}/debrief').json()
        else:
            final = client.post(f'/api/sessions/{sid}/skip-debrief').json()
        before = len(provider.calls)
        response = client.get(f'/api/sessions/{sid}/export.pdf')
        reader, text = read_pdf(response)
        assert len(provider.calls) == before
        assert final['case']['title'] in text
        assert 'Аня <b>& / ../../' in text
        assert len(reader.pages) >= (3 if review else 2)
        for index, message in enumerate(transcript['messages'], 1):
            assert f'{index:02d} ·' in text
            assert re.sub(r'\s+', ' ', message['text']) in re.sub(r'\s+', ' ', text)
        assert all(s not in text for s in SENTINELS)
        assert all(s not in response.headers['content-disposition'] for s in ('Аня', '../', '<b>'))
        assert 'Модератор' not in text and 'Moderator' not in text
        assert 'OPENROUTER_API_KEY' not in text and 'runtime_case' not in text
        review_title = 'Your review' if language == 'en' else 'Ваш разбор'
        review_pages = [i for i, page in enumerate(reader.pages) if review_title in page.extract_text()]
        assert bool(review_pages) == review
        if review:
            start = review_pages[0]
            assert start > 0
            assert all(message['text'] not in reader.pages[start].extract_text() for message in transcript['messages'] if message['speaker'] == 'opponent')
            report = final['debrief']
            for value in (report['summary'], report['next_step'], report['example_phrase']):
                if value:
                    assert re.sub(r'\s+', ' ', value) in re.sub(r'\s+', ' ', text)
        else:
            assert not any(c['purpose'] == 'judge' for c in provider.calls)


def test_pdf_guard_statuses_failure_and_safe_filename(tmp_path):
    provider = CompletionProvider()
    provider.judge_failure = True
    app, _ = make_test_app(tmp_path, provider, demo_access_code='offline-guard')
    with TestClient(app) as client:
        auth = _headers('offline-guard')
        session = client.post('/api/sessions', json=options(), headers=auth).json()
        sid = session['id']
        url = f'/api/sessions/{sid}'
        assert client.get(url + '/export.pdf').status_code == 401
        assert client.get(url + '/export.pdf', headers=_headers('wrong')).status_code == 401
        assert client.get(url + '/export.pdf', headers=auth).status_code == 409
        assert client.get('/api/sessions/missing/export.pdf', headers=auth).status_code == 404
        store = app.state.session_store
        store.reserve_message(sid, 'cancelled-pdf-turn', 'Несохранённый ответ не должен считаться полученным.')
        client.post(url + '/finish', headers=auth)
        assert client.post(url + '/debrief', headers=auth).status_code == 502
        before = len(provider.calls)
        _, text = read_pdf(client.get(url + '/export.pdf', headers=auth))
        assert 'Сессия завершена до ответа' in text
        assert 'Ваш разбор' not in text
        assert len(provider.calls) == before
        for status, label in [('pending', 'Ответ ожидается'), ('failed', 'Ответ не получен')]:
            with store._connection() as db:
                messages = store.get(sid)['messages']
                messages[-1]['delivery_status'] = status
                db.execute('UPDATE sessions SET messages_json = ? WHERE id = ?', (json.dumps(messages), sid))
            assert label in read_pdf(client.get(url + '/export.pdf', headers=auth))[1]
    assert export_filename({'id': '../../\r\nX:evil'}) == 'line-of-decision-Xevil.pdf'


def test_long_dialogue_markup_long_words_and_complete_feedback(tmp_path):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options()).json()
        sid = session['id']
        store = app.state.session_store
        for i in range(24):
            store.reserve_message(sid, f'long-pdf-turn-{i}', f'УНИКАЛЬНАЯРЕПЛИКА{i:03d} ' + ('Кириллица «в кавычках», переносы — читаемы.\n' * 60) + 'X' * 700)
            store.complete_message(sid, f'long-pdf-turn-{i}', f'ОТВЕТ{i:03d} Ответ содержит <tag> & текст.')
        client.post(f'/api/sessions/{sid}/finish')
        store.reserve_debrief(sid)
        store.complete_debrief(sid, {'summary': 'ПОЛНЫЙОТЗЫВ ' + 'Длинный разбор фактов. ' * 180,
            'strengths': [{'quote': 'УНИКАЛЬНАЯРЕПЛИКА000', 'explanation': 'СИЛЬНАЯСТОРОНА ' + 'Сохранённая рекомендация. ' * 90}],
            'risks': [{'quote': 'УНИКАЛЬНАЯРЕПЛИКА023', 'explanation': 'РИСК ' + 'Рекомендация. ' * 90}],
            'next_step': 'СЛЕДУЮЩИЙШАГ', 'example_phrase': 'ПРИМЕРФРАЗЫ'})
        before = len(provider.calls)
        reader, text = read_pdf(client.get(f'/api/sessions/{sid}/export.pdf'))
        assert len(reader.pages) > 20
        for i in range(24):
            assert f'УНИКАЛЬНАЯРЕПЛИКА{i:03d}' in text
            assert f'ОТВЕТ{i:03d}' in text
        for marker in ('ПОЛНЫЙОТЗЫВ', 'СИЛЬНАЯСТОРОНА', 'РИСК', 'СЛЕДУЮЩИЙШАГ', 'ПРИМЕРФРАЗЫ', '<tag> & текст.'):
            assert marker in text
        assert len(provider.calls) == before


def test_pdf_all_public_intro_fields_and_participants(tmp_path):
    provider = CompletionProvider()
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        session = client.post('/api/sessions', json=options(conflict_type='public')).json()
        sid = session['id']
        public = app.state.session_store.get(sid)['public']
        public['student_goal'] = 'ПУБЛИЧНАЯЗАДАЧА'
        with app.state.session_store._connection() as db:
            db.execute('UPDATE sessions SET public_json = ? WHERE id = ?', (json.dumps(public), sid))
        client.post(f'/api/sessions/{sid}/finish')
        _, text = read_pdf(client.get(f'/api/sessions/{sid}/export.pdf'))
        assert 'ПУБЛИЧНАЯЗАДАЧА' in text
        assert 'Участники' in text
        for participant in public['participants']:
            assert participant['name'] in text
        assert all(s not in text for s in SENTINELS)
