import { useCallback, useSyncExternalStore } from 'react';

import { addToBasket, clearBasket, getBasket, removeFromBasket, subscribeBasket } from '../services/api';
import type { BasketItem } from '../types';

export function useBasket() {
  const items = useSyncExternalStore(
    subscribeBasket,
    getBasket,
    (): BasketItem[] => [],
  );

  const add = useCallback((questionId: string) => {
    addToBasket(questionId);
  }, []);

  const remove = useCallback((questionId: string) => {
    removeFromBasket(questionId);
  }, []);

  const clear = useCallback(() => {
    clearBasket();
  }, []);

  return { items, count: items.length, add, remove, clear };
}
