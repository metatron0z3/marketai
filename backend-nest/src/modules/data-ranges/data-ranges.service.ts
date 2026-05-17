import { Injectable, Logger } from '@nestjs/common';
import { QuestdbService } from '../../database/questdb.service';
import { InstrumentsService } from '../instruments/instruments.service';
import { DataRangesResponseDto, DatatypeRangeDto, SymbolRangeDto } from './dto/data-range.dto';

@Injectable()
export class DataRangesService {
  private readonly logger = new Logger(DataRangesService.name);

  constructor(
    private readonly questdbService: QuestdbService,
    private readonly instrumentsService: InstrumentsService,
  ) {}

  async getDataRanges(): Promise<DataRangesResponseDto> {
    this.logger.log('Fetching data ranges for all instruments');

    const instruments = this.instrumentsService.findAll();
    const symbolRanges: SymbolRangeDto[] = [];

    for (const instrument of instruments) {
      try {
        const sql = `
          SELECT
            MIN(ts_event) as min_date,
            MAX(ts_event) as max_date
          FROM trades_data
          WHERE instrument_id = ${instrument.id}
        `;

        this.logger.debug(`Querying date range for ${instrument.symbol}`);
        const rows = await this.questdbService.query(sql);

        if (rows.length > 0 && rows[0].min_date && rows[0].max_date) {
          symbolRanges.push({
            symbol: instrument.symbol,
            instrument_id: instrument.id,
            start_date: this.formatDate(rows[0].min_date),
            end_date: this.formatDate(rows[0].max_date),
          });
        }
      } catch (error) {
        this.logger.error(`Error fetching range for ${instrument.symbol}: ${error.message}`);
      }
    }

    const tbboDatatype: DatatypeRangeDto = {
      datatype: 'TBBO',
      symbols: symbolRanges,
    };

    return {
      provider: 'databento',
      datatypes: [tbboDatatype],
    };
  }

  private formatDate(value: any): string {
    if (!value) return null;
    if (value instanceof Date) {
      return value.toISOString().split('T')[0];
    }
    return String(value).split('T')[0];
  }
}
