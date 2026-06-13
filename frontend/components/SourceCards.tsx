import type { Source } from '@/lib/types';

interface Props {
  sources: Source[];
}

export function SourceCards({ sources }: Props) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-2 space-y-1">
      <p className="text-xs text-text-muted uppercase tracking-wider">来源文章</p>
      <div className="flex flex-wrap gap-2">
        {sources.map((s, i) => (
          <div
            key={i}
            className="text-xs bg-bg-tertiary border border-border-primary rounded px-2 py-1 max-w-xs"
          >
            <div className="text-text-primary truncate">{s.title || '无标题'}</div>
            <div className="text-text-muted">
              {s.author && <span>{s.author}</span>}
              {s.date && <span className="ml-1 text-text-muted">· {s.date}</span>}
            </div>
            {s.url && (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent-blue hover:underline"
              >
                链接
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
