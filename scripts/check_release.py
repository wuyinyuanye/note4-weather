#!/usr/bin/env python3
"""Validate distributable paths, public defaults and artwork checksums."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {'.git', '.venv', '__pycache__', 'target', 'runtime'}


def release_files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not any(
        part in EXCLUDE for part in p.relative_to(ROOT).parts) and
        p.name not in {'config.json', '.DS_Store'})


def check():
    files = release_files()
    for p in files:
        rel = p.relative_to(ROOT)
        assert p.name not in {'album.py', 'test_album.py'}, rel
        assert p.suffix not in {'.log', '.jsonl', '.pid', '.bin', '.pem', '.key'}, rel
        if p.suffix == '.png':
            continue
        text = p.read_text(encoding='utf-8')
        assert not re.search(r'/(?:Users|home)/[A-Za-z0-9_-]+/', text), rel
        assert not re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', text), rel
        assert not re.search(r'gh[pousr]_[A-Za-z0-9]{20,}', text), rel
        assert not re.search(r'github_pat_[A-Za-z0-9_]{20,}', text), rel
        if 'vendor' not in rel.parts:
            assert not re.search(r'192\.168\.\d+\.\d+', text), rel
    config = json.loads((ROOT/'config.example.json').read_text())
    assert config['target'] == '192.0.2.10'
    assert config['expected_id'] == 'YOUR_DEVICE_ID'
    manifest = json.loads((ROOT/'assets/weather-realistic-v1/manifest.json').read_text())
    for spec in manifest['assets'].values():
        data = (ROOT/'assets/weather-realistic-v1'/spec['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == spec['sha256']
    print(f'Release checks passed: {len(files)} files; public defaults; weather-only; asset SHA-256 valid')
    return files


if __name__ == '__main__':
    check()
