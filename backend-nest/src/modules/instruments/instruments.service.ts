import { Injectable } from '@nestjs/common';
import { InstrumentDto } from './dto/instrument.dto';

@Injectable()
export class InstrumentsService {
  // Hardcoded symbols matching the original FastAPI backend
  private readonly SYMBOLS: Record<string, number> = {
    SPY: 15144,
    QQQ: 13340,
    TSLA: 16244,
  };

  findAll(): InstrumentDto[] {
    return Object.entries(this.SYMBOLS).map(([symbol, id]) => ({
      symbol,
      id,
    }));
  }

  findBySymbol(symbol: string): InstrumentDto | null {
    const upperSymbol = symbol.toUpperCase();
    if (this.SYMBOLS[upperSymbol]) {
      return {
        symbol: upperSymbol,
        id: this.SYMBOLS[upperSymbol],
      };
    }
    return null;
  }

  findById(id: number): InstrumentDto | null {
    for (const [symbol, instrumentId] of Object.entries(this.SYMBOLS)) {
      if (instrumentId === id) {
        return { symbol, id };
      }
    }
    return null;
  }
}
