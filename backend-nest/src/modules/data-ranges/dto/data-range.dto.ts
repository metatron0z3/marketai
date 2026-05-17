import { ApiProperty } from '@nestjs/swagger';

export class SymbolRangeDto {
  @ApiProperty({ example: 'SPY' })
  symbol: string;

  @ApiProperty({ example: 15144 })
  instrument_id: number;

  @ApiProperty({ example: '2024-01-02' })
  start_date: string;

  @ApiProperty({ example: '2024-12-31' })
  end_date: string;
}

export class DatatypeRangeDto {
  @ApiProperty({ example: 'TBBO' })
  datatype: string;

  @ApiProperty({ type: [SymbolRangeDto] })
  symbols: SymbolRangeDto[];
}

export class DataRangesResponseDto {
  @ApiProperty({ example: 'databento' })
  provider: string;

  @ApiProperty({ type: [DatatypeRangeDto] })
  datatypes: DatatypeRangeDto[];
}
