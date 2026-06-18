import type { Source } from '@/lib/types';

interface Props {
  sources: Source[];
}

export function SourceCards({ sources }: Props) {
  if (sources.length === 0) return null;

  const localSources = sources.filter(s => s.kind !== 'web');
  const webSources = sources.filter(s => s.kind === 'web');

  return (
    <div className="mt-2 space-y-2">
      {localSources.length > 0 && (
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">本地来源</p>
          <div className="flex flex-wrap gap-2">
            {localSources.map((s, i) => (
              <SourceCard key={`local-${i}`} source={s} />
            ))}
          </div>
        </div>
      )}
      {webSources.length > 0 && (
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">网络来源</p>
          <div className="flex flex-wrap gap-2">
            {webSources.map((s, i) => (
              <SourceCard key={`web-${i}`} source={s} variant="web" />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SourceCard({ source: s, variant }: { source: Source; variant?: 'web' }) {
  const borderClass = variant === 'web'
    ? 'border-blue-500/30 bg-blue-950/20'
    : 'border-border-primary bg-bg-tertiary';

  return (
    <div className={`text-xs border rounded px-2 py-1 max-w-xs ${borderClass}`}>
      <div className="flex items-center gap-1">
        {variant === 'web' && (
          <span className="text-[10px] bg-blue-500/20 text-blue-400 px-1 rounded">网络</span>
        )}
        <span className="text-text-primary truncate">{s.title || '无标题'}</span>
      </div>
      <div className="text-text-muted">
        {s.author && <span>{s.author}</span>}
        {s.date && <span className="ml-1">· {s.date}</span>}
      </div>
      {s.url && (
        <a
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent-blue hover:underline"
        >
          {variant === 'web' ? s.url.replace(/^https?:\/\//, '').split('/')[0] : '链接'}
        </a>
      )}
    </div>
  );
}
