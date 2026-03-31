// TypeScript interfaces mirroring seraph.api.schemas Pydantic models.

export interface ServiceStatus {
  name: string;
  ok: boolean;
  detail: string;
}

export interface HealthResponse {
  status: string;
  services: ServiceStatus[];
}

export interface EngagementSummary {
  engagement_id: string;
  target_ip: string;
  target_os: string;
  phase: string;
  flags_captured: number;
  findings_count: number;
  elapsed_seconds: number;
  started_at: string;
}

export interface Finding {
  [key: string]: unknown;
}

export interface EngagementDetail extends EngagementSummary {
  findings: Finding[];
  tool_outputs: Record<string, unknown>[];
  plan: Record<string, unknown>[];
}

export interface MachineResultResponse {
  name: string;
  os: string;
  difficulty: string;
  outcome: string;
  total_time_seconds: number;
  flags_captured: number;
  technique_accuracy: number;
  kb_utilization: number;
  error: string;
}

export interface BenchmarkRunResponse {
  run_id: string;
  generated_at: string;
  machine_count: number;
  solve_rate: number;
  partial_rate: number;
  avg_time_to_root_seconds: number | null;
  avg_technique_accuracy: number;
  avg_kb_utilization: number;
  results: MachineResultResponse[];
}

export interface TriggerBenchmarkRequest {
  machine?: string;
  difficulty?: string;
  run_all?: boolean;
  timeout_seconds?: number;
}

export interface TriggerBenchmarkResponse {
  run_id: string;
  task_id: string;
  status: string;
}

export interface CollectionStats {
  collection_name: string;
  points_count: number;
  vectors_count: number;
  indexed: boolean;
  status: string;
}

export interface IngestionSourceStatus {
  source: string;
  document_count: number;
  last_updated: string | null;
  errors: number;
  active: boolean;
}

export interface KnowledgeStatsResponse {
  collection: CollectionStats;
  ingestion: IngestionSourceStatus[];
}

export interface TrainingResultResponse {
  timestamp: string;
  triplets_used: number;
  final_loss: number;
  duration_seconds: number;
  adapter_path: string;
  success: boolean;
  error_message: string;
}

export interface LearningStatsResponse {
  feedback_records: number;
  triplets_total: number;
  triplets_pending: number;
  min_triplets_required: number;
  ready_to_train: boolean;
  last_training: TrainingResultResponse | null;
  training_history: TrainingResultResponse[];
}

export interface MachineResponse {
  name: string;
  ip: string;
  os: string;
  difficulty: string;
  expected_techniques: string[];
  has_real_flags: boolean;
}

export interface MachineCreateRequest {
  name: string;
  ip: string;
  os: string;
  difficulty: string;
  expected_techniques?: string[];
}

export interface WriteupSubmitResponse {
  task_id: string;
  filename: string;
  status: string;
  status_url: string;
}

export interface WriteupTaskStatus {
  task_id: string;
  state: string;
  result: Record<string, unknown> | null;
  error: string;
}

export interface ErrorResponse {
  error: string;
  detail: string;
  path: string;
}

// WebSocket message envelope
export interface WsMessage<T = unknown> {
  type: 'snapshot' | 'update';
  data: T;
}
