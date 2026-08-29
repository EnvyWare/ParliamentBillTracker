/**
 * The EnvyWare Prompt E, drawn inline.
 *
 * Inline rather than an `<img>` for three reasons: it costs no extra request,
 * it inherits the text colour so the E is white on Char and Char on Cream
 * without shipping two files, and it keeps the promise that this site loads no
 * remote asset of any kind.
 *
 * Two things here are brand rules rather than preferences, so neither is
 * parameterised:
 *
 * - The chevron is always Ember. It is the one full-strength Ember element on
 *   the page, which is why nothing else uses `--accent-loud`.
 * - The clear space is one arm height (10 units on the 64-unit grid) on all
 *   sides, and it is part of the viewBox so no layout can crop it.
 *
 * The mark is never recoloured, outlined, shadowed or placed inside a shape.
 */

const EMBER = '#FF5A1F';

interface EnvyWareMarkProps {
  /** Applied to the root `<svg>`; sizing lives in CSS. */
  readonly className?: string;
}

export function EnvyWareMark({ className }: EnvyWareMarkProps): React.JSX.Element {
  return (
    <svg
      className={className}
      viewBox="0 0 64 64"
      width="64"
      height="64"
      role="img"
      aria-label="EnvyWare"
      focusable="false"
    >
      {/* The E. `currentColor` is what makes it white on dark and Char on light. */}
      <rect x="10" y="8" width="40" height="10" rx="2" fill="currentColor" />
      <rect x="10" y="8" width="10" height="48" rx="2" fill="currentColor" />
      <rect x="10" y="46" width="40" height="10" rx="2" fill="currentColor" />
      {/* The middle arm is a terminal chevron: "E", and "ready for input". */}
      <polyline
        points="24,23 36,32 24,41"
        fill="none"
        stroke={EMBER}
        strokeWidth="9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
