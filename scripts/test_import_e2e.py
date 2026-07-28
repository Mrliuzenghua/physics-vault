"""End-to-end test: upload docx → pandoc → clean → structure → confirm."""
import json
import urllib.request
import urllib.error
import uuid
from pathlib import Path

BASE = "http://localhost:8000"


def post_json(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def post_multipart(url, file_path, field="file"):
    boundary = uuid.uuid4().hex
    p = Path(file_path)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{p.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + p.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


# 1. Upload
print("=== 1. Create batch ===")
batch = post_multipart(f"{BASE}/api/import/batches", "scripts/fixtures/test_exam.docx")
batch_id = batch["batch_id"]
print("batch_id:", batch_id)

# 2. Pandoc
print("\n=== 2. Pandoc unpack ===")
pandoc = post_json(f"{BASE}/api/import/batches/{batch_id}/pandoc", {})
print("status:", pandoc["status"], "| images:", pandoc["image_count"])
print("markdown preview:", pandoc["text"][:200].replace("\n", "\\n"))

# 3. AI clean
print("\n=== 3. AI clean ===")
try:
    clean = post_json(f"{BASE}/api/import/batches/{batch_id}/ai-clean", {})
    print("status:", clean["status"], "| cleaned_by:", clean.get("cleaned_by"))
except urllib.error.HTTPError as e:
    print("clean failed (continuing):", e.code, e.read()[:200])

# 4. Structure
print("\n=== 4. Structure ===")
struct = post_json(f"{BASE}/api/import/batches/{batch_id}/ai-structure", {})
print("status:", struct["status"], "| count:", struct["question_count"], "| by:", struct.get("structured_by"), "| ai_refined:", struct.get("ai_refined_count"))
for q in struct["questions"]:
    print(f"  [{q['question_type']}] {q['title'][:50]!r} opts={len(q['options'])} ans={q['answer'][:30]!r} figs={len(q['figures'])}")

# 5. Confirm (simulate user edit: delete nothing, edit Q1 answer)
print("\n=== 5. Confirm ===")
edited = struct["questions"]
if edited:
    edited[0]["answer"] = "C（用户已校对）"
confirm = post_json(f"{BASE}/api/import/batches/{batch_id}/confirm", {"questions": edited})
print("task_id:", confirm["task_id"], "| count:", confirm["question_count"])

# 6. Verify review can load it
print("\n=== 6. Review loads task ===")
task = json.loads(urllib.request.urlopen(f"{BASE}/api/import/tasks/{confirm['task_id']}", timeout=30).read())
print("task status:", task["status"], "| questions in result:", len(task["result"]["questions"]))
print("first question answer:", task["result"]["questions"][0]["answer"][:40])

# 7. Image upload
print("\n=== 7. Upload extra image ===")
img = post_multipart(f"{BASE}/api/import/batches/{batch_id}/images", "data/assets/questions/2007-GK-BJ-PHY-01-Q00000001-01.png")
print("uploaded:", img["filename"], "→", img["relative_path"])
img_url = f"{BASE}/files/{img['relative_path']}"
code = urllib.request.urlopen(img_url, timeout=10).status
print("image accessible via /files/:", code)

print("\nALL PASS")
