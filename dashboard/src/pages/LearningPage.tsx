import { useLearningStats } from '../hooks/useLearning';
import { FeedbackStatsCard } from '../components/learning/FeedbackStatsCard';
import { TrainingHistoryTable } from '../components/learning/TrainingHistoryTable';
import { LearningCurveChart } from '../components/benchmark/LearningCurveChart';
import { useBenchmarkRuns } from '../hooks/useBenchmarks';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';

export function LearningPage() {
  const { data, isLoading, error } = useLearningStats();
  const { data: runs } = useBenchmarkRuns();

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={String(error)} />;
  if (!data) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Feedback Loop
        </h2>
        <FeedbackStatsCard stats={data} />
      </section>

      {runs && runs.length > 1 && (
        <section>
          <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
            Learning Curve (Solve Rate Over Runs)
          </h2>
          <LearningCurveChart runs={runs} />
        </section>
      )}

      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Training History
        </h2>
        <TrainingHistoryTable history={data.training_history} />
      </section>
    </div>
  );
}
