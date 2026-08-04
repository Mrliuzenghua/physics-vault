import { create } from 'zustand';

import type { ComposeItem } from '../types';

const HISTORY_LIMIT = 60;

interface ComposeWorkbenchState {
  items: ComposeItem[];
  selectedIndex: number;
  past: ComposeItem[][];
  future: ComposeItem[][];
  transactionBaseline: ComposeItem[] | null;
  revision: number;
  savedRevision: number;
  loadItems: (items: ComposeItem[], selectedIndex?: number) => void;
  commitItems: (items: ComposeItem[], selectedIndex?: number) => void;
  updateItems: (updater: (items: ComposeItem[]) => ComposeItem[]) => void;
  beginTransaction: () => void;
  commitTransaction: () => void;
  cancelTransaction: () => void;
  selectIndex: (index: number) => void;
  undo: () => void;
  redo: () => void;
  markSaved: (revision?: number) => void;
}

function normalizeSelection(items: ComposeItem[], selectedIndex: number): number {
  if (items.length === 0) return -1;
  if (selectedIndex < 0) return -1;
  return Math.min(selectedIndex, items.length - 1);
}

export const useComposeWorkbenchStore = create<ComposeWorkbenchState>((set, get) => ({
  items: [],
  selectedIndex: -1,
  past: [],
  future: [],
  transactionBaseline: null,
  revision: 0,
  savedRevision: 0,

  loadItems: (items, selectedIndex = items.length > 0 ? 0 : -1) => {
    set({
      items,
      selectedIndex: normalizeSelection(items, selectedIndex),
      past: [],
      future: [],
      transactionBaseline: null,
      revision: 0,
      savedRevision: 0,
    });
  },

  commitItems: (items, selectedIndex) => {
    const state = get();
    const past = [...state.past, state.items].slice(-HISTORY_LIMIT);
    set({
      items,
      selectedIndex: normalizeSelection(items, selectedIndex ?? state.selectedIndex),
      past,
      future: [],
      transactionBaseline: null,
      revision: state.revision + 1,
    });
  },

  updateItems: (updater) => {
    const state = get();
    const items = updater(state.items);
    if (items === state.items) return;
    set({
      items,
      selectedIndex: normalizeSelection(items, state.selectedIndex),
      revision: state.revision + 1,
    });
  },

  beginTransaction: () => {
    const state = get();
    if (state.transactionBaseline) return;
    set({ transactionBaseline: state.items });
  },

  commitTransaction: () => {
    const state = get();
    if (!state.transactionBaseline) return;
    const changed = state.transactionBaseline !== state.items;
    set({
      transactionBaseline: null,
      past: changed ? [...state.past, state.transactionBaseline].slice(-HISTORY_LIMIT) : state.past,
      future: changed ? [] : state.future,
    });
  },

  cancelTransaction: () => {
    const state = get();
    if (!state.transactionBaseline) return;
    set({
      items: state.transactionBaseline,
      selectedIndex: normalizeSelection(state.transactionBaseline, state.selectedIndex),
      transactionBaseline: null,
      revision: state.revision + 1,
    });
  },

  selectIndex: (index) => {
    set((state) => ({ selectedIndex: normalizeSelection(state.items, index) }));
  },

  undo: () => {
    const state = get();
    const previous = state.past.at(-1);
    if (!previous) return;
    set({
      items: previous,
      selectedIndex: normalizeSelection(previous, state.selectedIndex),
      past: state.past.slice(0, -1),
      future: [state.items, ...state.future].slice(0, HISTORY_LIMIT),
      transactionBaseline: null,
      revision: state.revision + 1,
    });
  },

  redo: () => {
    const state = get();
    const next = state.future[0];
    if (!next) return;
    set({
      items: next,
      selectedIndex: normalizeSelection(next, state.selectedIndex),
      past: [...state.past, state.items].slice(-HISTORY_LIMIT),
      future: state.future.slice(1),
      transactionBaseline: null,
      revision: state.revision + 1,
    });
  },

  markSaved: (revision = get().revision) => set({ savedRevision: revision }),
}));

export function getComposeWorkbenchSnapshot() {
  return useComposeWorkbenchStore.getState();
}
