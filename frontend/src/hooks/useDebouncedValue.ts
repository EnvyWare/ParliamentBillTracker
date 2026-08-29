import { useEffect, useState } from 'react';

/**
 * Delay a rapidly changing value.
 *
 * Used for the free-text search box so filtering runs once the typing pauses
 * rather than on every keystroke.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    if (value === debounced) return;
    const timer = window.setTimeout(() => {
      setDebounced(value);
    }, delayMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value, delayMs, debounced]);

  return debounced;
}
