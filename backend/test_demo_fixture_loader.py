"""Fixture selection must retain normal auth and fail closed outside demo."""
from test_credit_card_document_assessment import postgres_demo
from route.demo_fixture_routes import _manifest


def test_demo_loader_disabled_and_authenticated(postgres_demo, monkeypatch):
    client = postgres_demo['client']
    headers = {'session-id': postgres_demo['borrower'].session_id}
    monkeypatch.delenv('PRISM_ENV', raising=False)
    monkeypatch.delenv('PRISM_DEMO_FIXTURES', raising=False)
    assert client.get('/demo-fixtures', headers=headers).status_code == 404
    monkeypatch.setenv('PRISM_ENV', 'demo')
    monkeypatch.setenv('PRISM_DEMO_FIXTURES', 'true')
    assert client.get('/demo-fixtures', headers={'session-id': 'invalid'}).status_code == 401
    manifest = client.get('/demo-fixtures', headers=headers).json()
    assert len(manifest['files']) == 24
    assert manifest['cutoff_month'] == '2026-09'
    banks = [i for i in manifest['files'] if i['category'] == 'bank']
    assert len(banks) == 6 and all(i['sha256'] for i in banks)
    item = banks[0]
    assert client.get(f"/demo-fixtures/bank/{item['name']}", headers=headers).content.startswith(b'%PDF')
    assert client.get('/demo-fixtures/bank/arbitrary.pdf', headers=headers).status_code == 404
    monkeypatch.setenv('PRISM_ENV', 'production')
    assert client.get('/demo-fixtures', headers=headers).status_code == 404


def test_fixture_manifest_hashes_and_categories():
    manifest = _manifest()
    assert set(i['category'] for i in manifest['files']) == {'bank', 'creditCards', 'salary', 'utility'}
