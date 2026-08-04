import { useCallback, useSyncExternalStore } from 'react';

import { addToBasket, clearBasket, getBasket, moveBasketItem, removeFromBasket, subscribeBasket } from '../services/api';
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

  const move = useCallback((questionId: string, direction: 'up' | 'down') => {
    moveBasketItem(questionId, direction);
  }, []);

  return { items, count: items.length, add, remove, clear, move };
}
