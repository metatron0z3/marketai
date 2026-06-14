/**
 * instruments.service.ts — dynamic instrument registry
 *
 * Two-layer lookup:
 *   1. KNOWN_SYMBOLS constant (always available, no DB dependency)
 *   2. Python service /instruments endpoint (adds DB-backed entries)
 */

import { Injectable, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { InstrumentDto } from './dto/instrument.dto';

const KNOWN_SYMBOLS: Record<string, { id: number; name: string; source: string }> = {
  // Databento IDs
  SPY:  { id: 15144, name: 'SPDR S&P 500 ETF',           source: 'databento' },
  QQQ:  { id: 13340, name: 'Invesco QQQ ETF',             source: 'databento' },
  TSLA: { id: 16244, name: 'Tesla Inc.',                   source: 'databento' },
  // yfinance IDs
  AAPL: { id: 10001, name: 'Apple Inc.',                   source: 'yfinance' },
  AMD:  { id: 10002, name: 'Advanced Micro Devices',       source: 'yfinance' },
  META: { id: 10003, name: 'Meta Platforms Inc.',          source: 'yfinance' },
  NVDA: { id: 10004, name: 'NVIDIA Corporation',           source: 'yfinance' },
  AMZN: { id: 10005, name: 'Amazon.com Inc.',              source: 'yfinance' },
  MSFT: { id: 10006, name: 'Microsoft Corporation',        source: 'yfinance' },
  GLD:  { id: 10007, name: 'SPDR Gold Shares',             source: 'yfinance' },
  TLT:  { id: 10008, name: 'iShares 20+ Year Treasury',   source: 'yfinance' },
};

@Injectable()
export class InstrumentsService {
  private readonly logger = new Logger(InstrumentsService.name);
  private readonly pythonServiceUrl: string;

  constructor(private readonly httpService: HttpService) {
    this.pythonServiceUrl = process.env.PYTHON_SERVICE_URL ?? 'http://python-service:8000';
  }

  async findAll(): Promise<InstrumentDto[]> {
    const merged = new Map<string, InstrumentDto>(
      Object.entries(KNOWN_SYMBOLS).map(([symbol, info]) => [
        symbol,
        { symbol, id: info.id, name: info.name, source: info.source },
      ]),
    );

    try {
      const { data } = await firstValueFrom(
        this.httpService.get<Array<{ symbol: string; id: number; name?: string; source?: string }>>(
          `${this.pythonServiceUrl}/api/v1/instruments/`,
        ),
      );
      for (const row of data) {
        merged.set(row.symbol, {
          symbol: row.symbol,
          id: row.id,
          name: row.name ?? '',
          source: row.source ?? 'unknown',
        });
      }
    } catch (err) {
      this.logger.warn('Could not fetch instruments from Python service — using fallback: ' + err.message);
    }

    return [...merged.values()].sort((a, b) => a.symbol.localeCompare(b.symbol));
  }

  findBySymbol(symbol: string): InstrumentDto | null {
    const upper = symbol.toUpperCase();
    const info = KNOWN_SYMBOLS[upper];
    if (!info) return null;
    return { symbol: upper, id: info.id, name: info.name, source: info.source };
  }

  findById(id: number): InstrumentDto | null {
    for (const [symbol, info] of Object.entries(KNOWN_SYMBOLS)) {
      if (info.id === id) return { symbol, id: info.id, name: info.name, source: info.source };
    }
    return null;
  }
}
