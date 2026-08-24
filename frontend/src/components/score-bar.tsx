const SEGMENTS = 10;

/**
 * The signature visual element: a 10-segment signal bar mirroring the
 * scoring rubric's 1-10 scale one-to-one, so the shape of the bar and the
 * number next to it always agree — no separate "meter" abstraction with
 * its own scale to keep in sync.
 */
export function ScoreBar({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <div className="flex items-center gap-2" aria-hidden="true">
        <div className="flex gap-[3px]">
          {Array.from({ length: SEGMENTS }).map((_, i) => (
            <span key={i} className="h-5 w-1.5 rounded-[1px] bg-border" />
          ))}
        </div>
        <span className="font-mono text-sm text-muted-foreground">&mdash;</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2" role="img" aria-label={`Fit score ${score} out of 10`}>
      <div className="flex gap-[3px]">
        {Array.from({ length: SEGMENTS }).map((_, i) => (
          <span
            key={i}
            className={
              i < score
                ? "h-5 w-1.5 rounded-[1px] bg-primary shadow-[0_0_6px_var(--primary)]"
                : "h-5 w-1.5 rounded-[1px] bg-border"
            }
          />
        ))}
      </div>
      <span className="font-mono text-sm font-medium tabular-nums text-foreground">
        {score}
        <span className="text-muted-foreground">/10</span>
      </span>
    </div>
  );
}
