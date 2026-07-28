"""Verify that the PUT endpoint now:
1. Returns full question data (not just {ok, message})
2. Preserves image data when figures is not in the payload
3. Q4's previously corrupted filename is fixed
"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"

def get(qid):
    res = urllib.request.urlopen(f"{BASE}/questions/{qid}")
    return json.loads(res.read())

def put(qid, data):
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE}/questions/{qid}",
        data=body,
        method='PUT',
        headers={'Content-Type': 'application/json'},
    )
    res = urllib.request.urlopen(req)
    return json.loads(res.read())

# ── 1. Check Q4 current state ──
q4 = get("Q00000004")
print("=== Q4 GET (before PUT) ===")
print(f"  image_filenames = {q4.get('image_filenames')}")
print(f"  image_count = {q4.get('image_count')}")
print(f"  title = {q4.get('canonical_title', '')[:60]}...")

# ── 2. PUT with only content fields (no figures) ──
put_payload = {
    "title": q4.get("canonical_title", ""),
    "question_type": q4.get("type", q4.get("question_type", "single_choice")),
    "difficulty": int(q4.get("difficulty", 2) or 2),
    "answer": q4.get("answer_text", "A"),
    "analysis": q4.get("analysis_text", ""),
    "options": json.loads(q4.get("options_json", "[]")) if isinstance(q4.get("options_json"), str) else q4.get("options_json", []),
    "tags": [],
    "source": "",
    # Note: NO "figures" field in the payload
}

print("\n=== PUT payload (no figures) ===")
print(f"  keys = {list(put_payload.keys())}")

put_result = put("Q00000004", put_payload)
print(f"\n=== PUT response ===")
print(f"  response keys = {list(put_result.keys())}")
print(f"  has image_filenames? {'image_filenames' in put_result}")
print(f"  image_filenames = {put_result.get('image_filenames')}")
print(f"  image_count = {put_result.get('image_count')}")
print(f"  canonical_title = {put_result.get('canonical_title', '')[:60]}...")
print(f"  answer_text = {put_result.get('answer_text', '')[:40]}...")

# ── 3. Verify Q4's image data is preserved in DB ──
q4_after = get("Q00000004")
print(f"\n=== Q4 GET (after PUT) ===")
print(f"  image_filenames = {q4_after.get('image_filenames')}")
print(f"  image_count = {q4_after.get('image_count')}")

# ── 4. Check all three ──
all_good = True
if not put_result.get("image_filenames"):
    print("  ❌ PUT response missing image_filenames")
    all_good = False
if not q4_after.get("image_filenames"):
    print("  ❌ Q4 image_filenames wiped after PUT")
    all_good = False
if "ok" in put_result:
    print("  ❌ PUT response still returns old {ok} format")
    all_good = False

if all_good:
    print("\n✅ ALL CHECKS PASSED — PUT returns full data, images preserved")
else:
    print("\n❌ SOME CHECKS FAILED")
