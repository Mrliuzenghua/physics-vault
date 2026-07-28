#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore Q00000001 to standard data (difficulty=1, clean analysis)."""
import json
import urllib.request
import urllib.error

BODY = {
    "question_id": "Q00000001",
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

req = urllib.request.Request(
    "http://127.0.0.1:8000/questions/Q00000001",
    data=json.dumps(BODY, ensure_ascii=False).encode("utf-8"),
    method="PUT",
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        print("RESTORE:", r.status, json.loads(r.read().decode("utf-8")))
except urllib.error.HTTPError as e:
    print("ERROR:", e.code, json.loads(e.read().decode("utf-8")))
