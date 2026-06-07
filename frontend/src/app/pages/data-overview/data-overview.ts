import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';

interface OptionsBarStat {
  symbol: string;
  calls_rows: number;
  puts_rows: number;
  total_rows: number;
  first_date: string | null;
  last_date: string | null;
}

interface SymbolStat {
  symbol: string;
  rows: number;
  first_date: string | null;
  last_date: string | null;
}

interface IngestRun {
  symbol: string;
  start_date: string;
  end_date: string;
  status: string;
  contracts_ingested: number;
  bars_written: number;
  started_at: string | null;
  finished_at: string | null;
}

interface Overview {
  generated_at: string;
  massive_options_bars: { symbols: OptionsBarStat[]; total_rows: number };
  massive_underlying_bars: { symbols: SymbolStat[]; total_rows: number };
  yfinance_equity: { symbols: SymbolStat[]; total_rows: number };
  databento_trades: { symbols: SymbolStat[]; total_rows: number };
  ml_pipeline: {
    options_features_rows: number;
    options_features_labeled: number;
    whale_features_rows: number;
    whale_features_labeled: number;
  };
  recent_ingest_runs: IngestRun[];
}

@Component({
  selector: 'app-data-overview',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './data-overview.html',
  styleUrl: './data-overview.scss',
})
export class DataOverviewPage implements OnInit {
  overview: Overview | null = null;
  loading = true;
  error: string | null = null;

  constructor(private api: ApiService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = null;
    this.api.getDataOverview().subscribe({
      next: (data) => {
        this.overview = data;
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.error = err.message ?? 'Failed to load data overview';
        this.loading = false;
        this.cdr.detectChanges();
      },
    });
  }

  fmt(n: number): string {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
    return String(n);
  }

  statusClass(status: string): string {
    if (status === 'completed') return 'status-ok';
    if (status === 'running') return 'status-running';
    return 'status-error';
  }

  labelPct(rows: number, labeled: number): string {
    if (!rows) return '—';
    return Math.round((labeled / rows) * 100) + '%';
  }
}
