import { ApiProperty } from '@nestjs/swagger';

export class OhlcvDto {
  @ApiProperty({ example: '2024-01-02T09:30:00.000000Z', description: 'Timestamp' })
  timestamp: string;

  @ApiProperty({ example: 15144, description: 'Instrument ID' })
  instrument_id: number;

  @ApiProperty({ example: 473.25, description: 'Opening price' })
  open: number;

  @ApiProperty({ example: 473.89, description: 'Highest price' })
  high: number;

  @ApiProperty({ example: 473.1, description: 'Lowest price' })
  low: number;

  @ApiProperty({ example: 473.5, description: 'Closing price' })
  close: number;

  @ApiProperty({ example: 125000, description: 'Trading volume' })
  volume: number;
}
