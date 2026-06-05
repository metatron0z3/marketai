import { Injectable, Logger } from '@nestjs/common';
import { QuestdbService } from '../../database/questdb.service';
import {
  DataOverviewResponseDto,
  OptionsBarSymbolStatDto,
  SymbolStatDto,
  IngestRunDto,
  MlPipelineDto,
} from './dto/data-overview.dto';

@Injectable()
export class DataOverviewService {
  private readonly logger = new Logger(DataOverviewService.name);

  constructor(private readonly questdb: QuestdbService) {}

  async getOverview(): Promise<DataOverviewResponseDto> {
    const [
      optionsBars,
      underlyingBars,
      yfinance,
      dbtoTrades,
      mlPipeline,
      ingestRuns,
    ] = await Promise.all([
      this.queryMassiveOptionsBars(),
      this.queryTable('underlying_bars', 'symbol', 'ts_event'),
      this.queryTable('yf_ohlcv_daily', 'symbol', 'ts'),
      this.queryTable('options_trades', 'symbol', 'ts_event'),
      this.queryMlPipeline(),
      this.queryIngestRuns(),
    ]);

    return {
      generated_at: new Date().toISOString(),
      massive_options_bars: {
        symbols: optionsBars,
        total_rows: optionsBars.reduce((s, r) => s + r.total_rows, 0),
      },
      massive_underlying_bars: {
        symbols: underlyingBars,
        total_rows: underlyingBars.reduce((s, r) => s + r.rows, 0),
      },
      yfinance_equity: {
        symbols: yfinance,
        total_rows: yfinance.reduce((s, r) => s + r.rows, 0),
      },
      databento_trades: {
        symbols: dbtoTrades,
        total_rows: dbtoTrades.reduce((s, r) => s + r.rows, 0),
      },
      ml_pipeline: mlPipeline,
      recent_ingest_runs: ingestRuns,
    };
  }

  private async queryMassiveOptionsBars(): Promise<OptionsBarSymbolStatDto[]> {
    try {
      const rows = await this.questdb.query<any>(`
        SELECT underlying_symbol, contract_type,
               COUNT(*) AS rows,
               MIN(ts_event) AS first_bar,
               MAX(ts_event) AS last_bar
        FROM options_bars
        GROUP BY underlying_symbol, contract_type
        ORDER BY underlying_symbol, contract_type
      `);

      // Pivot: merge call + put rows per symbol
      const map = new Map<string, OptionsBarSymbolStatDto>();
      for (const row of rows) {
        const sym = row.underlying_symbol as string;
        if (!map.has(sym)) {
          map.set(sym, {
            symbol: sym,
            calls_rows: 0,
            puts_rows: 0,
            total_rows: 0,
            first_date: null,
            last_date: null,
          });
        }
        const entry = map.get(sym)!;
        const count = Number(row.rows);
        if (row.contract_type === 'call') entry.calls_rows = count;
        else if (row.contract_type === 'put') entry.puts_rows = count;
        entry.total_rows += count;

        const first = this.fmt(row.first_bar);
        const last = this.fmt(row.last_bar);
        if (!entry.first_date || (first && first < entry.first_date)) entry.first_date = first;
        if (!entry.last_date || (last && last > entry.last_date)) entry.last_date = last;
      }
      return Array.from(map.values()).sort((a, b) => a.symbol.localeCompare(b.symbol));
    } catch (err) {
      this.logger.warn(`options_bars query failed: ${err.message}`);
      return [];
    }
  }

  private async queryTable(
    table: string,
    symbolCol: string,
    tsCol: string,
  ): Promise<SymbolStatDto[]> {
    try {
      const rows = await this.questdb.query<any>(`
        SELECT ${symbolCol} AS symbol,
               COUNT(*) AS rows,
               MIN(${tsCol}) AS first_bar,
               MAX(${tsCol}) AS last_bar
        FROM ${table}
        GROUP BY ${symbolCol}
        ORDER BY ${symbolCol}
      `);
      return rows.map((r) => ({
        symbol: String(r.symbol),
        rows: Number(r.rows),
        first_date: this.fmt(r.first_bar),
        last_date: this.fmt(r.last_bar),
      }));
    } catch (err) {
      this.logger.warn(`${table} query failed: ${err.message}`);
      return [];
    }
  }

  private async queryMlPipeline(): Promise<MlPipelineDto> {
    const safeCount = async (sql: string): Promise<number> => {
      try {
        const rows = await this.questdb.query<any>(sql);
        return rows.length > 0 ? Number(rows[0].rows) : 0;
      } catch {
        return 0;
      }
    };

    const [ofRows, ofLabeled, wfRows, wfLabeled] = await Promise.all([
      safeCount('SELECT COUNT(*) AS rows FROM options_features'),
      safeCount('SELECT COUNT(*) AS rows FROM options_features WHERE label_24h IS NOT NULL'),
      safeCount('SELECT COUNT(*) AS rows FROM whale_features'),
      safeCount('SELECT COUNT(*) AS rows FROM whale_features WHERE label_4w IS NOT NULL'),
    ]);

    return {
      options_features_rows: ofRows,
      options_features_labeled: ofLabeled,
      whale_features_rows: wfRows,
      whale_features_labeled: wfLabeled,
    };
  }

  private async queryIngestRuns(): Promise<IngestRunDto[]> {
    try {
      const rows = await this.questdb.query<any>(`
        SELECT underlying_symbol, start_date, end_date, status,
               contracts_ingested, bars_written, ts_started, ts_finished
        FROM options_ingest_runs
        ORDER BY ts_started DESC
        LIMIT 30
      `);
      return rows.map((r) => ({
        symbol: r.underlying_symbol,
        start_date: r.start_date,
        end_date: r.end_date,
        status: r.status,
        contracts_ingested: Number(r.contracts_ingested ?? 0),
        bars_written: Number(r.bars_written ?? 0),
        started_at: this.fmt(r.ts_started),
        finished_at: this.fmt(r.ts_finished),
      }));
    } catch (err) {
      this.logger.warn(`options_ingest_runs query failed: ${err.message}`);
      return [];
    }
  }

  private fmt(value: any): string | null {
    if (!value) return null;
    if (value instanceof Date) return value.toISOString().split('T')[0];
    return String(value).split('T')[0];
  }
}
