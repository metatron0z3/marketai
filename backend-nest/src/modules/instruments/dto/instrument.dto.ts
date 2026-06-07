import { ApiProperty } from '@nestjs/swagger';

export class InstrumentDto {
  @ApiProperty({ example: 'AAPL', description: 'Instrument symbol' })
  symbol: string;

  @ApiProperty({ example: 10001, description: 'Instrument ID' })
  id: number;

  @ApiProperty({ example: 'Apple Inc.', description: 'Human-readable name' })
  name?: string;

  @ApiProperty({ example: 'yfinance', description: 'Data source (databento | yfinance)' })
  source?: string;
}
