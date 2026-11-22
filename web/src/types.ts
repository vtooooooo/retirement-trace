export interface Evidence {
  id: string;
  person: string | null;
  kind: string;
  label: string;
  system: string;
  batch: string;
  ingested: string;
  version: number;
  validation: string;
  status?: string;
  identifier?: string;
  year?: number;
  address?: string;
  region?: string;
  cents?: number;
  obligation?: string;
}
export interface Alert {
  id: string;
  person: string;
  kind: string;
  title: string;
  severity: string;
  source: string;
  detected: string;
  version: string;
  supporting: string[];
  conflicting: string[];
  action: string;
}
export interface Match {
  id: string;
  person: string;
  left: string;
  right: string;
  score: number;
  status: string;
  version: string;
  agreements: string[];
  conflicts: string[];
}
export interface Action {
  name: string;
  evidence: string[];
  gain: number;
  effort: number;
  risk: number;
  reliability: number;
  impact: number;
  approval: string;
  score: number;
  version: string;
  uncertainty: string;
}
export interface Entry {
  actor: string;
  kind: string;
  at: string;
  version: number;
  note: string;
  state: string;
  reference?: string;
}
export interface Case {
  id: string;
  person: string;
  name: string;
  alert: Alert;
  state: string;
  assignee: string | null;
  created: string;
  version: number;
  actions: Action[];
  evidence: string[];
  timeline: Entry[];
}
export type Counts = Record<string, number>;
export interface Dataset {
  as_of: string;
  version: string;
  evidence: Record<string, Evidence>;
  cases: Case[];
  matches: Match[];
  metrics: {
    total: number;
    open: number;
    review: number;
    high: number;
    awaiting: number;
    uncashed: number;
    resolved: number;
    reviewed_identities: number;
    average_age: number;
    aging: Counts;
    statuses: Counts;
    throughput: Counts;
    categories: Counts;
    workload: Counts;
  };
  benchmark: {
    ingestion: {
      participants: number;
      sources: number;
      records: number;
      seed: number;
      alerts: number;
      by_kind: Counts;
    };
    identity: Record<string, Counts>;
    curve: Counts[];
    split_counts: number[];
    rules: Counts;
    investigation: {
      cases: number;
      policies: Record<string, Counts>;
      assumptions: string;
    };
  };
}
