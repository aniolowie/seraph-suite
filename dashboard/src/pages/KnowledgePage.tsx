import { useKnowledgeStats } from '../hooks/useKnowledge';
import { CollectionStatsCard } from '../components/knowledge/CollectionStatsCard';
import { IngestionProgressBar } from '../components/knowledge/IngestionProgressBar';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';

export function KnowledgePage() {
  const { data, isLoading, error } = useKnowledgeStats();

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={String(error)} />;
  if (!data) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Vector Store
        </h2>
        <CollectionStatsCard stats={data.collection} />
      </section>

      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Ingestion Sources
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {data.ingestion.map((s) => (
            <IngestionProgressBar key={s.source} source={s} />
          ))}
        </div>
      </section>
    </div>
  );
}
