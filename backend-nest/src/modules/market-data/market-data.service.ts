import { Injectable, Logger } from '@nestjs/common';
import { QuestdbService } from '../../database/questdb.service';
import { MarketDataQueryDto } from './dto/market-data-query.dto';
import { OhlcvDto } from './dto/ohlcv.dto';

@Injectable()
export class MarketDataService {
  private readonly logger = new Logger(MarketDataService.name);

  // Map timeframe to QuestDB sample interval
  private readonly timeframeMap: Record<string, string> = {
    '5min': '5m',
    '1hour': '1h',
    '1day': '1d',
  };

  constructor(private readonly questdbService: QuestdbService) {}

  async getMarketData(query: MarketDataQueryDto): Promise<OhlcvDto[]> {
    const { instrument_id, timeframe = '5min', start_date, end_date } = query;
    const sampleInterval = this.timeframeMap[timeframe] || '5m';

    this.logger.log(
      `Fetching market data: instrument=${instrument_id}, timeframe=${timeframe}, start=${start_date}, end=${end_date}`,
    );

    // Build the query
    let sql = `
      SELECT
        ts_event as timestamp,
        instrument_id,
        first(price) as open,
        max(price) as high,
        min(price) as low,
        last(price) as close,
        sum(size) as volume
      FROM trades_data
      WHERE instrument_id = ${instrument_id}
    `;

    // Add date filters if provided
    if (start_date) {
      sql += ` AND ts_event >= '${start_date}T00:00:00.000000Z'`;
    }
    if (end_date) {
      sql += ` AND ts_event <= '${end_date}T23:59:59.999999Z'`;
    }

    sql += `
      SAMPLE BY ${sampleInterval}
      ALIGN TO CALENDAR
    `;

    this.logger.debug(`Executing query: ${sql}`);

    try {
      const rows = await this.questdbService.query(sql);

      // Convert to OhlcvDto format
      const result: OhlcvDto[] = rows.map((row) => ({
        timestamp: this.formatTimestamp(row.timestamp),
        instrument_id: row.instrument_id,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
        volume: row.volume,
      }));

      this.logger.log(`Returning ${result.length} aggregated OHLCV records`);
      return result;
    } catch (error) {
      this.logger.error(`Error fetching market data: ${error.message}`, error.stack);
      throw error;
    }
  }

  private formatTimestamp(value: any): string {
    if (!value) return null;
    if (value instanceof Date) {
      return value.toISOString();
    }
    return String(value);
  }
}
