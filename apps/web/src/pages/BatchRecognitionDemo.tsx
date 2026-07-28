import BatchRecognitionPanel from '../components/recognition/BatchRecognitionPanel';

/**
 * Demo page for the redesigned batch-recognition popup.
 * Showcases an improved version of the sjep.net /!/exam recognition popup.
 */
export default function BatchRecognitionDemo() {
  return (
    <div
      className="flex h-full flex-col overflow-y-auto"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* Intro banner — shows the problem and the improvement */}
      <div
        className="flex-shrink-0 px-6 py-4 border-b"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
      >
        <div className="mx-auto" style={{ maxWidth: 1100 }}>
          <div className="flex items-center gap-2 mb-1">
            <span
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold"
              style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}
            >
              <span>改进版</span>
            </span>
            <h1 className="text-base font-bold" style={{ color: 'var(--color-text)' }}>
              批量智能识别弹窗
            </h1>
          </div>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)', maxWidth: 720 }}>
            对照 sjep.net/!/exam 原始弹窗的 UX 问题（垂直文字、错误状态简陋、信息层级混乱），重写为清晰三栏布局、水平排版、零旋转文字、可见的整体/单份进度、可逐份重试。
          </p>
        </div>
      </div>

      {/* Centered panel on neutral background — mimics modal-on-page state */}
      <div className="flex-1 flex items-center justify-center px-6 py-10">
        <div className="w-full" style={{ maxWidth: 1100 }}>
          <BatchRecognitionPanel />
        </div>
      </div>

      {/* Improvement notes */}
      <div
        className="flex-shrink-0 px-6 py-4 border-t"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
      >
        <div className="mx-auto" style={{ maxWidth: 1100 }}>
          <div className="text-[11px] font-semibold uppercase mb-2" style={{ color: 'var(--color-text-muted)', letterSpacing: '0.08em' }}>
            主要改进
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            <ImprovementItem before="垂直 90° 旋转文字" after="水平排版 + 状态徽章" />
            <ImprovementItem before="拥挤的彩色 tab 堆叠" after="顶部 stats chips（已完成/失败/进行中）" />
            <ImprovementItem before="错误状态为纯文本" after="图标 + 描述 + 每份重试 + 全部重试" />
            <ImprovementItem before="竖排数字按钮 1-6" after="文档列表 + 单击预览题目/进度" />
            <ImprovementItem before="无整体进度" after="底部总进度条 + 计数统计" />
            <ImprovementItem before="无内嵌上传" after="拖拽到左侧即加入队列" />
          </div>
        </div>
      </div>
    </div>
  );
}

function ImprovementItem({ before, after }: { before: string; after: string }) {
  return (
    <div className="rounded-md border px-2.5 py-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}>
      <div style={{ color: 'var(--color-red)' }}>
        <span style={{ fontWeight: 600 }}>原：</span> {before}
      </div>
      <div style={{ color: 'var(--color-green)' }}>
        <span style={{ fontWeight: 600 }}>改：</span> {after}
      </div>
    </div>
  );
}