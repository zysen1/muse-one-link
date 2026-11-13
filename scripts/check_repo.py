#!/usr/bin/env python3
"""Validate published entry points, local links and reproducible sample data."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
files = [p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.parts]
for path in files:
    if path.suffix == '.json':
        try:
            json.loads(path.read_text())
        except (ValueError, UnicodeError) as exc:
            errors.append(f'{path.relative_to(ROOT)}: invalid JSON: {exc}')
    if path.suffix != '.md':
        continue
    text = path.read_text()
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
        target = target.strip().strip('<>')
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        resolved = (path.parent / unquote(parsed.path)).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.exists():
            errors.append(f'{path.relative_to(ROOT)}: broken local link: {target}')
    for private_path in ('/Users/', '/home/mac/', 'codex://threads/'):
        if private_path in text:
            errors.append(f'{path.relative_to(ROOT)}: private workspace reference')
    if re.search(r'(?<!\d)1[3-9]\d{9}(?!\d)', text):
        errors.append(f'{path.relative_to(ROOT)}: review possible personal phone number')
    if re.search(r'gh[pousr]_[A-Za-z0-9]{30,}', text):
        errors.append(f'{path.relative_to(ROOT)}: possible GitHub token')

catalog = json.loads((ROOT / 'catalog.json').read_text())
if {c['id'] for c in catalog['cases']} != {'video', 'cloud', 'digest', 'grocery'}:
    errors.append('catalog must contain the four cases')
for case in catalog['cases']:
    path = ROOT / case['entry']
    if not path.is_file():
        errors.append(f'missing case entry: {case["entry"]}')
        continue
    text = path.read_text()
    for required in ('../../AGENTS.md', '../../docs/BUILD.md', '验收'):
        if required not in text:
            errors.append(f'{case["entry"]}: missing {required}')
    expected = catalog['repository'] + '/tree/main/cases/' + case['id']
    if case['url'] != expected:
        errors.append(f'case URL mismatch: {case["id"]}')

grocery = json.loads((ROOT / 'examples/grocery.json').read_text())
base = grocery['baseline']
for test in grocery['acceptanceCases']:
    inventory = {i['ingredientId']: i['quantity'] for i in base['inventory']}
    inventory.update(test['inventoryOverrides'])
    demand = {key: 0 for key in inventory}
    for meal in base['meals']:
        if meal['id'] in test['selectedMealIds']:
            for item in meal['ingredients']:
                demand[item['ingredientId']] += item['quantity']
    actual = {key: max(value - inventory.get(key, 0), 0) for key, value in demand.items()}
    if actual != test['expectedShortage']:
        errors.append(f'grocery fixture mismatch: {test["id"]}: {actual}')
video = json.loads((ROOT / 'examples/video-project.json').read_text())
if video['status'] != 'planned' or video['outputs'] or any(s['candidates'] for s in video['shots']):
    errors.append('video example must remain an unexecuted plan')

if errors:
    print('\n'.join(errors), file=sys.stderr)
    sys.exit(1)
print(f'OK: {len(files)} files; 4 case entries; local links; JSON; 3 grocery scenarios; unexecuted video fixture.')
print('This is repository validation, not a live Muse integration test.')
