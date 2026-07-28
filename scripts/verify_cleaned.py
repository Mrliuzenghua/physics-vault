#!/usr/bin/env python3
"""通过 API 验证清洗后的数据"""
import urllib.request
import json

BASE = "http://127.0.0.1:8000"

# 测试几条代表性的题目
test_ids = ["Q00000001", "Q00000004", "Q00000005", "Q00000013", "Q00000015"]

for qid in test_ids:
    try:
        res = urllib.request.urlopen(f"{BASE}/questions/{qid}")
        data = json.loads(res.read())
        
        print(f"[{qid}]")
        print(f"  canonical_title = {repr(data.get('canonical_title', 'N/A'))[:100]}")
        print(f"  title_text      = {repr(data.get('title_text', 'N/A'))[:60]}")
        
        opts = data.get("options_json") or data.get("options") or "[]"
        if isinstance(opts, str):
            opts = json.loads(opts)
        print(f"  options ({len(opts)}项):")
        for o in opts[:2]:
            print(f"    {o}")
        if len(opts) > 2:
            print(f"    ... ({len(opts)-2} more)")
        
        answer = data.get("answer_text", "N/A")
        has_img = "{{img" in str(answer)
        print(f"  answer_text = {repr(answer)[:80]}  {'⚠️有占位符!' if has_img else '✅'}")
        
        print(f"  image_count = {data.get('image_count', 'N/A')}")
        filenames = data.get("image_filenames_json") or data.get("image_filenames") or "[]"
        if isinstance(filenames, str):
            filenames = json.loads(filenames)
        print(f"  image_filenames = {filenames[:2]}{'...' if len(filenames)>2 else ''}")
        print()
    except Exception as e:
        print(f"[{qid}] ERROR: {e}\n")
