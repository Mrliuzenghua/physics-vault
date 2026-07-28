"""Probe what the list/search API returns for image fields."""
import json
import urllib.request

res = urllib.request.urlopen('http://127.0.0.1:8000/questions?limit=2')
data = json.loads(res.read())
items = data if isinstance(data, list) else data.get('items', data.get('questions', []))
for item in items[:2]:
    qid = item.get('question_id', '?')
    print(f"\n=== {qid} (list API) ===")
    for k in sorted(item.keys()):
        if any(w in k.lower() for w in ['image', 'asset', 'figure', 'file']):
            val = item[k]
            print(f"  {k} = {json.dumps(val, ensure_ascii=False)[:200]} (type={type(val).__name__})")
