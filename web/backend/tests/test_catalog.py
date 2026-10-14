from html.parser import HTMLParser

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class CatalogLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = []
        self.assets = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'a' and 'gh-card' in values.get('class', '').split():
            self.cards.append(values['href'])
        if tag in {'link', 'img', 'script'}:
            self.assets.append(values.get('href') or values.get('src'))


def demo_app(tmp_path):
    return create_app(settings=Settings(llm_mode='mock', database_path=str(tmp_path / 'catalog.sqlite3')))


def test_catalog_and_every_asset_work_on_the_same_future_domain_without_model_calls(tmp_path):
    app = demo_app(tmp_path)
    with TestClient(app, base_url='https://demo.example.test') as client:
        response = client.get('/games')
        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']
        assert client.get('/games/').text == response.text
        parsed = CatalogLinks()
        parsed.feed(response.text)
        assert parsed.cards == ['/games/line-decision']
        assert response.text.count('data-copy="demo"') == 1
        assert 'Демо-версия' in response.text
        assert parsed.assets
        for url in parsed.assets:
            assert url.startswith('/catalog-assets/')
            asset = client.get(url)
            assert asset.status_code == 200
            assert not asset.headers['content-type'].startswith('text/html')
        assert '127.0.0.1' not in response.text
        assert 'exercises.skillslab.center' not in response.text
    assert app.state.provider.calls == []


def test_catalog_game_link_serves_existing_app_and_keeps_api_on_the_same_origin(tmp_path):
    with TestClient(demo_app(tmp_path), base_url='https://demo.example.test') as client:
        game = client.get('/games/line-decision')
        assert game.status_code == 200
        assert game.text == client.get('/').text
        assert client.get('/games/line-decision/').text == game.text
        assert client.get('/api/health').json()['status'] == 'ok'
