"""E2E test with image-containing docx."""
import json
import urllib.request
import uuid
from pathlib import Path

BASE = "http://localhost:8000"


def post_json(url, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else b""
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def post_multipart(url, file_path):
    boundary = uuid.uuid4().hex
    p = Path(file_path)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{p.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + p.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


batch = post_multipart(f"{BASE}/api/import/batches", "scripts/fixtures/test_exam_img.docx")
batch_id = batch["batch_id"]
print("batch:", batch_id)

pandoc = post_json(f"{BASE}/api/import/batches/{batch_id}/pandoc")
print("pandoc:", pandoc["status"], "| images:", pandoc["image_count"])
for img in pandoc["images"]:
    print("  ", img["filename"], "→", img["relative_path"])

try:
    post_json(f"{BASE}/api/import/batches/{batch_id}/ai-clean")
except Exception as e:
    print("clean skipped:", e)

struct = post_json(f"{BASE}/api/import/batches/{batch_id}/ai-structure")
print("\nstructure:", struct["status"], "| count:", struct["question_count"])
for q in struct["questions"]:
    print(f"\n[{q['question_type']}] opts={len(q['options'])} ans={q['answer'][:20]!r}")
    print(f"  title: {q['title'][:100]!r}")
    print(f"  figures: {q['figures']}")

# Verify figure images are accessible
for q in struct["questions"]:
    for fig in q["figures"]:
        url = f"{BASE}/files/{fig['local_path']}"
        code = urllib.request.urlopen(url, timeout=10).status
        print(f"  /files/{fig['local_path']} → {code}")
