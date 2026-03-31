import { useState } from 'react';
import { useCreateMachine, useDeleteMachine, useMachines } from '../hooks/useMachines';
import { MachineTable } from '../components/machines/MachineTable';
import { MachineForm } from '../components/machines/MachineForm';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';

export function MachinesPage() {
  const { data: machines, isLoading, error } = useMachines();
  const create = useCreateMachine();
  const del = useDeleteMachine();
  const [showForm, setShowForm] = useState(false);

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={String(error)} />;

  const handleDelete = (name: string) => {
    if (window.confirm(`Delete machine "${name}"?`)) {
      del.mutate(name);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: '#888', fontSize: 13 }}>{machines?.length ?? 0} machines registered</span>
        <button
          onClick={() => setShowForm((v) => !v)}
          style={{
            background: showForm ? '#2d2d44' : '#7c4dff',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            padding: '8px 16px',
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          {showForm ? 'Cancel' : '+ Add Machine'}
        </button>
      </div>

      {showForm && (
        <div
          style={{
            background: '#1a1a2e',
            border: '1px solid #2d2d44',
            borderRadius: 8,
            padding: 16,
          }}
        >
          <h3 style={{ color: '#aaa', margin: '0 0 12px', fontSize: 13, textTransform: 'uppercase' }}>
            New Machine
          </h3>
          {create.error && <ErrorBanner message={String(create.error)} />}
          <MachineForm
            onSubmit={(data) => {
              create.mutate(data, { onSuccess: () => setShowForm(false) });
            }}
            loading={create.isPending}
          />
        </div>
      )}

      <MachineTable machines={machines ?? []} onDelete={handleDelete} />
    </div>
  );
}
