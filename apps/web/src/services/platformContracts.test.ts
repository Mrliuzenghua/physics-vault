import assert from 'node:assert/strict';
import test from 'node:test';

import type { ClassroomReflection } from './classroomReflection.ts';
import { listSavedHandoutVersions } from './lessonDocumentApi.ts';
import { listLessonReflections, saveLessonReflection } from './lessonReflectionApi.ts';
import { searchQuestions, updateQuestion } from './questionApi.ts';
import { fetchTeachingProject, listTeachingProjects } from './teachingProjectApi.ts';

test('teaching-project client clamps list limits and maps a missing project to null', async () => {
  const originalFetch = globalThis.fetch;
  const urls: string[] = [];
  globalThis.fetch = async (input) => {
    urls.push(String(input));
    if (String(input).includes('missing%2Fproject')) {
      return new Response(JSON.stringify({ detail: '教学项目不存在' }), { status: 404 });
    }
    return new Response(JSON.stringify({ items: [{ id: 'project-1' }] }), { status: 200 });
  };

  try {
    const projects = await listTeachingProjects(-8);
    assert.equal(projects[0]?.id, 'project-1');
    assert.equal(urls[0], '/api/teaching-projects?limit=1');
    assert.equal(await fetchTeachingProject('missing/project'), null);
    assert.equal(urls[1], '/api/teaching-projects/missing%2Fproject');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('lesson-reflection client keeps local synchronization fields out of the HTTP payload', async () => {
  const originalFetch = globalThis.fetch;
  let payload: unknown;
  globalThis.fetch = async (_input, init) => {
    payload = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ reflection: { id: 'reflection-1', projectId: 'project-1' } }), { status: 200 });
  };
  const reflection = {
    id: 'reflection-1',
    projectId: 'project-1',
    rating: 4,
    completed: true,
    highlights: '重点清晰',
    followUp: '增加练习',
    attendedPages: 8,
    createdAt: '2026-08-10T00:00:00Z',
    updatedAt: '2026-08-10T00:00:00Z',
    remoteUpdatedAt: '2026-08-10T00:00:00Z',
    remoteSyncState: 'pending',
  } satisfies ClassroomReflection;

  try {
    await saveLessonReflection(reflection, reflection.remoteUpdatedAt);
    assert.deepEqual(payload, {
      reflection: {
        id: 'reflection-1', projectId: 'project-1', rating: 4, completed: true,
        highlights: '重点清晰', followUp: '增加练习', attendedPages: 8,
        createdAt: '2026-08-10T00:00:00Z', updatedAt: '2026-08-10T00:00:00Z',
      },
      base_updated_at: '2026-08-10T00:00:00Z',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('lesson-document client encodes document IDs and returns the version DTO list', async () => {
  const originalFetch = globalThis.fetch;
  let url = '';
  globalThis.fetch = async (input) => {
    url = String(input);
    return new Response(JSON.stringify({
      document_kind: 'saved_handout', document_id: 'handout/1',
      items: [{ version: 2, version_id: 'handout-1-v2', created_at: '2026-08-10T00:00:00Z', title: '讲义', current: true }],
    }), { status: 200 });
  };

  try {
    const versions = await listSavedHandoutVersions('handout/1');
    assert.equal(url, '/api/lesson-documents/saved-handouts/handout%2F1/versions');
    assert.equal(versions[0]?.version_id, 'handout-1-v2');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('lesson-reflection client encodes project filters and bounds its limit', async () => {
  const originalFetch = globalThis.fetch;
  let url = '';
  globalThis.fetch = async (input) => {
    url = String(input);
    return new Response(JSON.stringify({ items: [] }), { status: 200 });
  };

  try {
    assert.deepEqual(await listLessonReflections('project / 1', 900), []);
    assert.equal(url, '/api/lesson-reflections?limit=500&project_id=project+%2F+1');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('question client preserves search normalization and excludes media fields from a question update', async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; body?: string }> = [];
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), body: typeof init?.body === 'string' ? init.body : undefined });
    if (String(input).startsWith('/search/questions')) {
      return new Response(JSON.stringify([{ question_id: 'question-1', title: '弹簧题' }]), { status: 200 });
    }
    return new Response(JSON.stringify({ question_id: 'question/1', title: '已更新', figures: [] }), { status: 200 });
  };

  try {
    const search = await searchQuestions({ query: '弹簧', limit: 5, offset: 0, search_mode: 'browse' });
    assert.equal(search.items[0]?.title, '弹簧题');
    assert.match(requests[0]?.url || '', /^\/search\/questions\?/);
    assert.match(requests[0]?.url || '', /include_facets=false/);

    await updateQuestion('question/1', {
      title: '已更新',
      figures: [{ fig_uuid: 'asset-1', local_path: 'data/gallery/asset-1.png' }],
      image_asset_ids: ['asset-1'],
    });
    assert.equal(requests[1]?.url, '/questions/question%2F1');
    assert.deepEqual(JSON.parse(requests[1]?.body || '{}'), { title: '已更新' });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
