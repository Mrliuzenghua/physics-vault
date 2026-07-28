"""Probe PUT /questions/Q00000001 to see real backend error."""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"

# 1) GET the question
with urllib.request.urlopen(f"{BASE}/questions/Q00000001") as r:
    d = json.loads(r.read())

# 2) Build the exact body the frontend sends (using normalizeQuestion mapping)
body = {
    "question_id": d.get("question_id"),
    "title": d.get("stem_text") or d.get("canonical_title") or "",
    "question_type": d.get("type") or d.get("question_type") or "",
    "difficulty": d.get("difficulty"),
    "source": d.get("primary_paper_id") or d.get("source") or "",
    "year": d.get("year"),
    "answer": d.get("answer_text") or d.get("answer") or "",
    "analysis": d.get("analysis_text") or d.get("analysis") or "",
    "tags": d.get("tags") or [],
    "options": d.get("options") or [],
    "knowledge_point": d.get("knowledge_point") or "",
    "figures": d.get("figures") or [],
    "sub_questions": d.get("sub_questions") or [],
}

print("=== PUT body (sent) ===")
print(json.dumps(body, ensure_ascii=False, indent=2)[:1500])
print()

# 3) PUT
req = urllib.request.Request(
    f"{BASE}/questions/Q00000001",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
try:
    with urllib.request.urlopen(req) as r:
        print(f"=== HTTP {r.status} (success) ===")
        print(r.read().decode("utf-8")[:2000])
except urllib.error.HTTPError as e:
    print(f"=== HTTP {e.code} (error) ===")
    body_text = e.read().decode("utf-8", errors="replace")
    print(body_text[:2000])
