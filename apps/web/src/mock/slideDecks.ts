/**
 * 课堂 PPT mock 数据
 *
 * 所有 mock 数据均使用 types/slides.ts 中定义的标准数据结构。
 * 页面组件只消费类型，不关心数据来源（mock / API / AI 生成）。
 */

import type { SlideDeck } from '../types/slides';

// ── 暑假学案 · 第02节 · 运动学图像与综合问题 ──────────────────────

export const MOCK_SLIDE_DECK_02: SlideDeck = {
  id: 'summer-02-kinematics-graph',
  title: '暑假学案',
  subtitle: '第02节 · 运动学图像与综合问题',
  theme: 'physics',
  pages: [
    // ── 第 1 页：知识概览 ──
    {
      id: 'page-02-1',
      pageType: 'knowledge_summary',
      title: '运动学图像核心知识',
      subtitle: 'x-t 图 · v-t 图 · a-t 图',
      badge: '知识梳理',
      layout: 'grid_2x2',
      sections: [
        {
          id: 'sec-1-x-t',
          type: 'summary',
          title: 'x-t 图像（位移-时间）',
          items: [
            { text: '斜率 = 速度 v', highlight: true },
            { text: '直线 → 匀速；曲线 → 变速' },
            { text: '纵截距 = 初始位置 x₀', icon: '📍' },
            { text: '交点 = 相遇时刻', icon: '🔀' },
          ],
        },
        {
          id: 'sec-1-v-t',
          type: 'summary',
          title: 'v-t 图像（速度-时间）',
          items: [
            { text: '斜率 = 加速度 a', highlight: true },
            { text: '面积 = 位移 Δx' },
            { text: '纵截距 = 初速度 v₀', icon: '📍' },
            { text: '交点 = 速度相同时刻' },
          ],
        },
        {
          id: 'sec-1-a-t',
          type: 'summary',
          title: 'a-t 图像（加速度-时间）',
          items: [
            { text: '面积 = 速度变化量 Δv' },
            { text: '水平线 → 匀变速运动' },
            { text: '正负号 = 加速度方向' },
          ],
        },
        {
          id: 'sec-1-method',
          type: 'method',
          title: '读图三步法',
          items: [
            { text: '① 看坐标轴：确认 x/v/a 哪种图', highlight: true, icon: '👁' },
            { text: '② 看斜率：匀速？匀变速？变加速？', icon: '📐' },
            { text: '③ 看面积（v-t / a-t）：求位移或速度变化', icon: '📏' },
          ],
        },
      ],
      footer: '运动学图像 · 核心知识',
    },

    // ── 第 2 页：方法总结 ──
    {
      id: 'page-02-2',
      pageType: 'method_summary',
      title: '图像问题常用方法',
      subtitle: '从图像中提取运动信息',
      badge: '方法总结',
      layout: 'two_column',
      sections: [
        {
          id: 'sec-2-methods',
          type: 'method',
          title: '四种经典解法',
          items: [
            {
              text: '斜率法：通过图像斜率直接读出速度或加速度',
              highlight: true,
              icon: '📐',
            },
            {
              text: '面积法：v-t 图面积 = 位移；a-t 图面积 = Δv',
              icon: '📏',
            },
            {
              text: '公式联立法：图像信息 → 运动学公式 → 求解未知量',
              icon: '📝',
              children: [
                { text: 'v = v₀ + at' },
                { text: 'x = v₀t + ½at²' },
                { text: 'v² - v₀² = 2ax' },
              ],
            },
            {
              text: '分段分析法：多段运动逐段处理，注意转折点',
              icon: '🔀',
            },
          ],
        },
        {
          id: 'sec-2-formulas',
          type: 'formula',
          title: '核心公式',
          items: [
            { text: '匀变速直线运动', formula: 'v = v_0 + at' },
            { text: '位移公式', formula: 'x = v_0 t + \\frac{1}{2} a t^2' },
            { text: '速度-位移关系', formula: 'v^2 - v_0^2 = 2 a x' },
            { text: '平均速度', formula: '\\bar{v} = \\frac{v_0 + v}{2} = \\frac{x}{t}' },
          ],
        },
      ],
      footer: '方法总结 · 运动学图像',
    },

    // ── 第 3 页：易错提醒 ──
    {
      id: 'page-02-3',
      pageType: 'warning_summary',
      title: '易错提醒 & 避坑指南',
      subtitle: '考试中最容易犯的 5 个错误',
      badge: '易错警示',
      layout: 'single_column',
      sections: [
        {
          id: 'sec-3-warnings',
          type: 'warning',
          title: '常见错误与纠正',
          items: [
            {
              text: '❌ 把 x-t 图的斜率当成加速度',
              highlight: true,
              icon: '⚠️',
              children: [
                { text: '✅ x-t 图斜率 = 速度，不是加速度！' },
              ],
            },
            {
              text: '❌ 把 v-t 图的纵坐标当成位移',
              highlight: true,
              icon: '⚠️',
              children: [
                { text: '✅ v-t 图纵坐标 = 瞬时速度，面积才是位移' },
              ],
            },
            {
              text: '❌ 忽略图像的"拐点"含义',
              icon: '⚠️',
              children: [
                { text: '✅ 拐点 = 加速度方向改变或运动性质变化' },
              ],
            },
            {
              text: '❌ 图像在时间轴下方的处理错误',
              icon: '⚠️',
              children: [
                { text: '✅ 时间轴下方 → 反向运动 / 负方向位移，面积要带符号' },
              ],
            },
            {
              text: '❌ 混淆 a-t 图面积与 v-t 图面积的含义',
              icon: '⚠️',
              children: [
                { text: '✅ a-t 图面积 = Δv；v-t 图面积 = Δx' },
              ],
            },
          ],
        },
        {
          id: 'sec-3-check',
          type: 'method',
          title: '自查清单',
          columns: 2,
          items: [
            { text: '确认图像类型（x-t / v-t / a-t）', icon: '☑️' },
            { text: '看清坐标轴单位和标度', icon: '☑️' },
            { text: '标注关键点（起点、拐点、交点）', icon: '☑️' },
            { text: '分段写出运动方程再求解', icon: '☑️' },
          ],
        },
      ],
      footer: '避坑指南 · 运动学图像',
    },

    // ── 第 4 页：图像知识专项 ──
    {
      id: 'page-02-4',
      pageType: 'example_intro',
      title: '图像知识进阶',
      subtitle: '追击相遇问题 · 图像综合应用',
      badge: '图像知识',
      layout: 'hero_with_sidebar',
      sections: [
        {
          id: 'sec-4-main',
          type: 'example',
          title: '追击相遇的图像解法',
          items: [
            {
              text: '两物体 x-t 图像的交点 = 相遇位置与时刻',
              highlight: true,
              icon: '🔀',
            },
            {
              text: 'v-t 图像中两曲线间的面积差 = 相对位移',
              icon: '📏',
            },
            {
              text: '速度相等时刻往往是"最远/最近"的临界点',
              highlight: true,
              icon: '⚡',
            },
          ],
        },
        {
          id: 'sec-4-figure',
          type: 'figure',
          title: '典型图像对比',
          items: [
            {
              text: '匀加速直线运动 v-t 图',
              imagePath: 'data/assets/questions/v-t-uniform-accel.png',
              imageAlt: '匀加速直线运动 v-t 图像示意',
            },
            {
              text: '追击问题两车 v-t 对比图',
              imagePath: 'data/assets/questions/v-t-chase.png',
              imageAlt: '追击问题 v-t 对比示意',
            },
          ],
        },
      ],
      footer: '图像进阶 · 运动学综合',
    },
  ],
};
