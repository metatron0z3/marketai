export class SymbolStatDto {
  symbol: string;
  rows: number;
  first_date: string | null;
  last_date: string | null;
}

export class OptionsBarSymbolStatDto {
  symbol: string;
  calls_rows: number;
  puts_rows: number;
  total_rows: number;
  first_date: string | null;
  last_date: string | null;
}

export class IngestRunDto {
  symbol: string;
  start_date: string;
  end_date: string;
  status: string;
  contracts_ingested: number;
  bars_written: number;
  started_at: string | null;
  finished_at: string | null;
}

export class MlPipelineDto {
  options_features_rows: number;
  options_features_labeled: number;
  whale_features_rows: number;
  whale_features_labeled: number;
}

export class TableSectionDto {
  symbols: SymbolStatDto[];
  total_rows: number;
}

export class DataOverviewResponseDto {
  generated_at: string;
  massive_options_bars: { symbols: OptionsBarSymbolStatDto[]; total_rows: number };
  massive_underlying_bars: TableSectionDto;
  yfinance_equity: TableSectionDto;
  databento_trades: TableSectionDto;
  ml_pipeline: MlPipelineDto;
  recent_ingest_runs: IngestRunDto[];
}
