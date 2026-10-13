"""Authenticated file selection only. Never injects assessments or scores."""
import hashlib
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database.db import get_db
from route.experimental_assessment_routes import _session_owner

router = APIRouter(prefix='/demo-fixtures', tags=['Development synthetic fixtures'])
ROOT = Path(__file__).resolve().parents[2] / 'tests/fixtures/prism_demo_validated'


def _enabled():
    if os.getenv('PRISM_ENV', '').lower() not in {'development', 'demo'} or os.getenv('PRISM_DEMO_FIXTURES') != 'true':
        raise HTTPException(404, 'Development fixture loader is disabled')


def _manifest():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    for item in manifest['files']:
        path = ROOT / item['name']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise HTTPException(409, 'Synthetic fixture hash mismatch')
    return manifest


@router.get('')
def fixture_manifest(session_id: str = Header(...), db: Session = Depends(get_db)):
    _enabled()
    _session_owner(session_id, db)
    return _manifest()


@router.get('/{category}/{name}')
def fixture_file(category: str, name: str, session_id: str = Header(...), db: Session = Depends(get_db)):
    _enabled()
    _session_owner(session_id, db)
    item = next((item for item in _manifest()['files'] if item['category'] == category and item['name'] == name), None)
    if item is None:
        raise HTTPException(404, 'Unknown synthetic fixture')
    return FileResponse(ROOT / item['name'], media_type='application/pdf', filename=name)
