"""Final verification: API image fields + file serving."""
import json
import urllib.request

print("=== 1. Detail API image fields ===")
res = urllib.request.urlopen('http://127.0.0.1:8000/questions/Q00000001')
data = json.loads(res.read())
print(f"  Q1: image_filenames={data.get('image_filenames')} count={data.get('image_count')}")

print("\n=== 2. Search API image fields ===")
res = urllib.request.urlopen('http://127.0.0.1:8000/search/questions?search_mode=browse&limit=5')
data = json.loads(res.read())
for item in data['items'][:5]:
    qid = item.get('question_id', '?')
    figs = item.get('figures', [])
    icount = item.get('image_count', 0)
    print(f"  {qid}: figures={figs[:2]} count={icount}")

print("\n=== 3. File serving (VAULT_ROOT fix) ===")
res = urllib.request.urlopen('http://127.0.0.1:8000/questions/Q00000001')
data = json.loads(res.read())
if data.get('image_filenames'):
    fname = data['image_filenames'][0]
    url = f'http://127.0.0.1:8000/files/data/assets/questions/{fname}'
    try:
        res = urllib.request.urlopen(url, timeout=5)
        content = res.read(200)
        ct = res.headers.get('content-type', '?')
        print(f"  OK {res.status} {fname} bytes={len(content)} content-type={ct}")
    except Exception as e:
        print(f"  FAIL {fname} -> {e}")

print("\n=== 4. File serving for Q13 (6 images) ===")
res = urllib.request.urlopen('http://127.0.0.1:8000/questions/Q00000013')
data = json.loads(res.read())
for fname in data.get('image_filenames', [])[:3]:
    url = f'http://127.0.0.1:8000/files/data/assets/questions/{fname}'
    try:
        res = urllib.request.urlopen(url, timeout=5)
        print(f"  OK {res.status} {fname}")
    except Exception as e:
        print(f"  FAIL {fname} -> {e}")
