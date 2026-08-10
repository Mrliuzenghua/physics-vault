/** Find the next item in the active review queue without leaving that queue. */
export function findNextMatchingIndex<T>(
  items: readonly T[],
  currentIndex: number,
  matches: (item: T, index: number) => boolean,
): number | null {
  const candidates = items
    .map((item, index) => ({ item, index }))
    .filter(({ item, index }) => index !== currentIndex && matches(item, index));

  return candidates.find(({ index }) => index > currentIndex)?.index
    ?? candidates[0]?.index
    ?? null;
}
