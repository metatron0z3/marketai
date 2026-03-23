import { ApiProperty } from '@nestjs/swagger';

export class InstrumentDto {
  @ApiProperty({ example: 'SPY', description: 'Instrument symbol' })
  symbol: string;

  @ApiProperty({ example: 15144, description: 'Instrument ID' })
  id: number;
}
