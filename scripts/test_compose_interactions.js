/* Interaction test: insert menu, text editing, undo. */
const { chromium } = require('playwright');

(async () => {
  const questionIds = [
    'batch_20260728_224417_1789e4_q0001',
    'batch_20260728_224417_1789e4_q0002',
    'batch_20260728_224417_1789e4_q0003',
  ];

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 950 } });
  const page = await context.newPage();
  page.on('pageerror', (err) => console.log('[pageerror]', String(err).slice(0, 300)));

  await page.goto('http://127.0.0.1:5173/browse', { waitUntil: 'domcontentloaded' });
  await page.evaluate((ids) => {
    const items = ids.map((question_id) => ({ question_id, added_at: new Date().toISOString() }));
    localStorage.setItem('physics_vault_basket', JSON.stringify(items));
  }, questionIds);
  await page.goto('http://127.0.0.1:5173/compose', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);

  // 1. Open insert menu and add a text block
  await page.getByRole('button', { name: /插入/ }).first().click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'output/compose_insert_menu.png' });
  await page.getByRole('button', { name: /正文文本块/ }).click();
  await page.waitForTimeout(1200);

  // 2. Text block is auto-selected -> inspector should show 文本 tab
  await page.screenshot({ path: 'output/compose_text_editor.png' });

  // 3. Edit the text content
  const textarea = page.locator('textarea').first();
  await textarea.fill('本讲目标：掌握运动学图像的斜率与面积含义，能独立完成 x-t / v-t 图像互译。');
  await page.waitForTimeout(900);

  // 4. Undo twice (should remove text edit history? no — text edits bypass history; undo should remove the inserted block)
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(600);

  // 5. Redo
  await page.keyboard.press('Control+y');
  await page.waitForTimeout(600);
  await page.screenshot({ path: 'output/compose_after_undo_redo.png' });

  // 6. Style tab fixed?
  await page.getByRole('button', { name: '样式' }).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'output/compose_style_tab.png' });

  await browser.close();
  console.log('done');
})();
