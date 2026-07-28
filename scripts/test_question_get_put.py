#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-round GET/PUT test for question Q00000001.

Round 1: GET  -> show current (broken) field mapping
Round 2: PUT  -> send standardised data (title/options/answer/analysis split)
Round 3: GET  -> verify fields now correspond correctly
Round 4: PUT  -> tweak analysis, retest update path
Round 5: GET  -> verify update persisted
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
QID = "Q00000001"


def http(method, path, body=None):
    url = f"{BASE}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def show(label, obj):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    if isinstance(obj, dict):
        for k in [
            "question_id", "canonical_title", "type", "question_type",
            "difficulty", "options_json", "stem_text", "answer_text",
            "analysis_text", "knowledge_point", "primary_paper_id",
            "tags_json", "status", "ok", "message",
        ]:
            if k in obj:
                v = obj[k]
                if isinstance(v, str) and len(v) > 120:
                    v = v[:120] + " …[truncated]"
                print(f"  {k}: {v!r}")
        # show any extra keys for debugging
        extras = {k: obj[k] for k in obj if k not in {
            "question_id", "canonical_title", "type", "question_type",
            "difficulty", "options_json", "stem_text", "answer_text",
            "analysis_text", "knowledge_point", "primary_paper_id",
            "tags_json", "status", "ok", "message",
            "module", "topic2", "topic3", "has_media",
            "primary_question_no", "vault_markdown_path", "knowledge_points",
            "content_hash", "schema_version", "created_at", "updated_at",
            "source_id", "image_asset_ids", "image_filenames", "image_count",
            "stem_clean_text", "tips_text", "similarity",
            "keyword_match", "search_mode", "score", "question_id",
        }}
        if extras:
            print(f"  (extra keys: {list(extras.keys())})")
    else:
        print(f"  {obj!r}")


def main():
    # ── Round 1: GET current (broken) data ──
    print("\n" + "#"*70)
    print("# ROUND 1: GET current data (expect field misalignment)")
    print("#"*70)
    st, got = http("GET", f"/questions/{QID}")
    print(f"\nHTTP {st}")
    show("BEFORE — current DB row (key fields)", got)
    print(f"\n  options_json is: {got.get('options_json')!r}")
    print(f"  stem_text contains 【答案】? {'【答案】' in (got.get('stem_text') or '')}")
    print(f"  stem_text contains 【解析】? {'【解析】' in (got.get('stem_text') or '')}")
    print(f"  answer_text (separate field): {got.get('answer_text')!r}")
    print(f"  analysis_text (separate field): {(got.get('analysis_text') or '')[:60]!r}…")

    # ── Round 2: PUT standardised data ──
    print("\n" + "#"*70)
    print("# ROUND 2: PUT standardised data (title/options/answer/analysis split)")
    print("#"*70)
    standard_body = {
        "question_id": QID,
        "title": "光导纤维的结构如图所示，其内芯和外套材料不同，光在内芯中传播。以下关于光导纤维的说法正确的是（　　）",
        "question_type": "single_choice",
        "difficulty": 1,
        "options": [
            {"opt": "A", "content": "内芯的折射率比外套大，光传播时在内芯与外套的界面发生全反射"},
            {"opt": "B", "content": "内芯的折射率比外套小，光传播时在内芯与外套的界面发生全反射"},
            {"opt": "C", "content": "内芯的折射率比外套小，光传播时在内芯与外套的界面发生折射"},
            {"opt": "D", "content": "内芯的折射率与外套相同，外套的材料有韧性，可以起保护作用"},
        ],
        "answer": "A",
        "analysis": "发生全反射的条件是光由光密介质射入光疏介质，所以内芯的折射率大，且光传播在内芯与外套的界面上发生全反射。\n\n故选A。",
        "sub_questions": [],
        "figures": [],
        "tags": ["全反射", "光导纤维", "折射率"],
        "knowledge_point": "T3-OPT-008",
        "source": "IMPORT",
        "review_status": "confirmed",
    }
    print(f"\nSending PUT body (standardised):")
    print(json.dumps(standard_body, ensure_ascii=False, indent=2))

    st, put_resp = http("PUT", f"/questions/{QID}", standard_body)
    print(f"\nHTTP {st}")
    show("PUT response", put_resp)

    if st != 200:
        print("\n❌ PUT failed, stopping.")
        return

    # ── Round 3: GET to verify standardisation persisted ──
    print("\n" + "#"*70)
    print("# ROUND 3: GET to verify fields now correspond correctly")
    print("#"*70)
    st, got2 = http("GET", f"/questions/{QID}")
    print(f"\nHTTP {st}")
    show("AFTER PUT — DB row (key fields)", got2)

    # Field-by-field verification
    print("\n  ── Field correspondence check ──")
    opts_raw = got2.get("options_json", "[]")
    try:
        opts = json.loads(opts_raw) if isinstance(opts_raw, str) else opts_raw
    except Exception:
        opts = []
    print(f"  options_json parsed ({len(opts)} items): {opts}")
    stem = got2.get("stem_text") or ""
    print(f"  stem_text starts with title? {stem.startswith(standard_body['title'][:30])}")
    print(f"  stem_text contains 【答案】A? {'【答案】A' in stem}")
    print(f"  stem_text contains 【解析】? {'【解析】' in stem}")
    print(f"  answer_text: {got2.get('answer_text')!r}")
    print(f"  analysis_text: {(got2.get('analysis_text') or '')[:80]!r}")
    print(f"  canonical_title (should be title[:100]): {got2.get('canonical_title')!r}")

    ok = (
        len(opts) == 4
        and opts[0].get("opt") == "A"
        and got2.get("answer_text") == "A"
        and got2.get("analysis_text", "").startswith("发生全反射")
        and got2.get("canonical_title") == standard_body["title"]
    )
    print(f"\n  {'✅ Round 3 PASS — fields correspond correctly' if ok else '❌ Round 3 FAIL'}")

    # ── Round 4: PUT a small edit (tweak analysis + difficulty) ──
    print("\n" + "#"*70)
    print("# ROUND 4: PUT small edit (bump difficulty to 2, append to analysis)")
    print("#"*70)
    edit_body = {
        "question_id": QID,
        "title": standard_body["title"],
        "question_type": "single_choice",
        "difficulty": 2,
        "options": standard_body["options"],
        "answer": "A",
        "analysis": "发生全反射的条件是光由光密介质射入光疏介质，所以内芯的折射率大，且光传播在内芯与外套的界面上发生全反射。\n\n故选A。\n\n【补充】光导纤维的内芯折射率 n₁ > 外套折射率 n₂，临界角 C = arcsin(n₂/n₁)。",
        "sub_questions": [],
        "figures": [],
        "tags": ["全反射", "光导纤维", "折射率", "临界角"],
        "knowledge_point": "T3-OPT-008",
        "source": "IMPORT",
        "review_status": "confirmed",
    }
    st, put2 = http("PUT", f"/questions/{QID}", edit_body)
    print(f"\nHTTP {st}")
    show("PUT edit response", put2)

    # ── Round 5: GET to verify edit persisted ──
    print("\n" + "#"*70)
    print("# ROUND 5: GET to verify edit persisted")
    print("#"*70)
    st, got3 = http("GET", f"/questions/{QID}")
    print(f"\nHTTP {st}")
    show("AFTER EDIT — DB row (key fields)", got3)

    print("\n  ── Edit verification ──")
    print(f"  difficulty (expect '2'): {got3.get('difficulty')!r}")
    print(f"  analysis contains 【补充】? {'【补充】' in (got3.get('analysis_text') or '')}")
    print(f"  tags count (expect 4): {len(got3.get('tags_json', '[]')) if got3.get('tags_json') else 'n/a'}")
    ok2 = (
        str(got3.get("difficulty")) == "2"
        and "【补充】" in (got3.get("analysis_text") or "")
    )
    print(f"\n  {'✅ Round 5 PASS — edit persisted' if ok2 else '❌ Round 5 FAIL'}")

    # ── Final summary ──
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Round 1 GET (before):     options_json={'[]' if got.get('options_json')=='[]' else 'has data'}, "
          f"stem混入答案={'是' if '【答案】' in (got.get('stem_text') or '') else '否'}")
    print(f"  Round 2 PUT standardise:   HTTP {st}, {put2.get('message') if isinstance(put2, dict) else put2}")
    print(f"  Round 3 GET (after):       options={len(opts)}项, fields对应={'✅' if ok else '❌'}")
    print(f"  Round 4 PUT edit:          HTTP {st}")
    print(f"  Round 5 GET (after edit):  difficulty={got3.get('difficulty')}, edit持久化={'✅' if ok2 else '❌'}")
    print("\nDone. Open http://localhost:5173/question/Q00000001 to see the fixed data in the UI.")


if __name__ == "__main__":
    main()
