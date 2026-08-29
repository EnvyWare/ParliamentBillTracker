import { useEffect, useState } from 'react';

/**
 * Track a CSS media query from JavaScript.
 *
 * Used only where layout genuinely changes behaviour rather than appearance:
 * below 768px the two route panels become collapsible, and only the first is
 * expanded. Everything else responsive is handled in CSS.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const list = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent): void => {
      setMatches(event.matches);
    };
    setMatches(list.matches);
    list.addEventListener('change', onChange);
    return () => {
      list.removeEventListener('change', onChange);
    };
  }, [query]);

  return matches;
}

export const NARROW_QUERY = '(max-width: 767px)';
