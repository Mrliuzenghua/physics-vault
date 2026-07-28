import urllib.request, json, os
from pathlib import Path

# 1. 测试 /files/ 端点
paths_to_try = [
    'data/assets/questions/2007-GK-BJ-PHY-01-Q00000001-01.png',
    'assets/questions/2007-GK-BJ-PHY-01-Q00000001-01.png',
    '2007-GK-BJ-PHY-01-Q00000001-01.png',
]
print('=== /files/ endpoint tests ===')
for p in paths_to_try:
    try:
        req = urllib.request.Request(f'http://127.0.0.1:8000/files/{p}', method='HEAD')
        res = urllib.request.urlopen(req, timeout=3)
        print(f'  OK ({res.status}) {p}')
    except Exception as e:
        print(f'  FAIL {p} -> {e}')

# 2. /questions/Q00000013/assets 端点
print()
print('=== /questions/Q00000013/assets ===')
try:
    res = urllib.request.urlopen('http://127.0.0.1:8000/questions/Q00000013/assets')
    data = json.loads(res.read())
    print(f'  count={len(data)}')
    for item in data[:3]:
        print(f'  {json.dumps(item, ensure_ascii=False)[:200]}')
except Exception as e:
    print(f'  ERROR: {e}')

# 3. VAULT_ROOT 推算
api_file = Path('apps/api/src/physics_vault_api/legacy_app.py').resolve()
API_ROOT = api_file.parents[1]
VAULT_ROOT = API_ROOT.parents[1]
print()
print('=== Path resolution ===')
print(f'  legacy_app.py = {api_file}')
print(f'  API_ROOT (parents[1]) = {API_ROOT}')
print(f'  VAULT_ROOT (parents[1] again) = {VAULT_ROOT}')
print(f'  VAULT_ROOT exists = {VAULT_ROOT.exists()}')
img_target = VAULT_ROOT / 'data/assets/questions/2007-GK-BJ-PHY-01-Q00000001-01.png'
print(f'  image at VAULT_ROOT/data/... = {img_target.exists()}')
img_target2 = Path('data/assets/questions/2007-GK-BJ-PHY-01-Q00000001-01.png').resolve()
print(f'  actual image location = {img_target2}')

# 4. 看前端实际拿到的 figures 字段（list vs detail）
print()
print('=== Frontend actual received fields ===')
# list 接口
try:
    res = urllib.request.urlopen('http://127.0.0.1:8000/questions?limit=3')
    lst = json.loads(res.read())
    items = lst if isinstance(lst, list) else lst.get('items', lst.get('questions', []))
    for it in items[:3]:
        qid = it.get('question_id')
        figs = it.get('figures')
        ifn = it.get('image_filenames')
        ic = it.get('image_count')
        print(f'  LIST {qid}: figures={figs!r} image_filenames={ifn!r} image_count={ic}')
except Exception as e:
    print(f'  list ERROR: {e}')

# detail 接口
for qid in ['Q00000005', 'Q00000013']:
    try:
        res = urllib.request.urlopen(f'http://127.0.0.1:8000/questions/{qid}')
        d = json.loads(res.read())
        figs = d.get('figures')
        ifn = d.get('image_filenames')
        ic = d.get('image_count')
        print(f'  DETAIL {qid}: figures={figs!r} image_filenames={ifn!r} image_count={ic}')
    except Exception as e:
        print(f'  detail {qid} ERROR: {e}')
