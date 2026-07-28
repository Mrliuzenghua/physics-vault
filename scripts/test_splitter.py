"""Test ExamQuestionSplitter on realistic pandoc output."""
import sys
sys.path.insert(0, "apps/api/src")

# Stub out package __init__ import chain issues by direct module load
import importlib.util
spec = importlib.util.spec_from_file_location(
    "question_splitter",
    "apps/api/src/physics_vault_api/services/question_splitter.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ExamQuestionSplitter = mod.ExamQuestionSplitter

SAMPLE = r"""
2025年高三物理第一次模拟考试

1\. 一质量为 $m=2\,\text{kg}$ 的物体静止在光滑水平面上。$t=0$ 时刻开始受到水平方向恒力 $F=10\,\text{N}$ 的作用。求：
(1) 物体的加速度大小；
(2) $t=3\,\text{s}$ 时物体的速度大小。

【答案】(1) $5\,\text{m/s}^2$ (2) $15\,\text{m/s}$

【解析】由牛顿第二定律 $F=ma$ 得加速度，再由 $v=at$ 得速度。

2、两个点电荷 $q_1$ 和 $q_2$ 相距 $r$，它们之间的库仑力大小为 $F$。若将 $q_1$ 的电荷量增大为原来的 3 倍，$q_2$ 的电荷量增大为原来的 2 倍，同时将距离变为原来的 2 倍，则库仑力大小变为：

A. $\frac{3}{2}F$
B. $\frac{3}{4}F$
C. $\frac{3}{8}F$
D. $6F$

答案：A

解析：由库仑定律 $F=k\frac{q_1q_2}{r^2}$。

（3）如图所示，一凸透镜的焦距为 $f=10\,\text{cm}$。
![](media/image3.png){width="2.5in" height="1.8in"}
物体放在透镜前 $u=15\,\text{cm}$ 处，成像情况为：

A. 正立放大的虚像  B. 倒立放大的实像  C. 倒立缩小的实像  D. 不成像

【答案】B

4．下列说法正确的是（多选）：

A. 物体的速度为零时，加速度一定为零
B. 物体的加速度减小时，速度可能增大
C. 物体的速度变化量越大，加速度越大
D. 物体的加速度方向与速度变化量方向相同

【答案】BD
【解析】加速度是速度变化率，与速度大小无关。

第5题 在"用单摆测量重力加速度"实验中：
(1) 实验需要测量的物理量有哪些？
(2) 若摆长 $l=1.00\,\text{m}$，测得周期 $T=2.01\,\text{s}$，求 $g$。

参考答案：(1) 摆长和周期 (2) $9.78\,\text{m/s}^2$
"""

media = [
    {
        "image_id": "image_0003",
        "filename": "image3.png",
        "relative_path": "data/import-batches/batch_test/pandoc/media/image3.png",
        "absolute_path": "x",
        "size": 100,
    }
]

splitter = ExamQuestionSplitter()
result = splitter.split(SAMPLE, "batch_test", "test.docx", media)

import json
for q in result["questions"]:
    print("=" * 60)
    print(f"Q{q['question_no']} [{q['question_type']}] id={q['question_id']}")
    print(f"  stem: {q['title'][:80]!r}...")
    print(f"  options: {[(o['opt'], o['content'][:30]) for o in q['options']]}")
    print(f"  answer: {q['answer'][:60]!r}")
    print(f"  analysis: {q['analysis'][:60]!r}")
    print(f"  figures: {q['figures']}")
