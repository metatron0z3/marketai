import { IsInt, IsOptional, IsString, IsIn } from 'class-validator';
import { Type } from 'class-transformer';
import { ApiPropertyOptional, ApiProperty } from '@nestjs/swagger';

export class IndicatorsQueryDto {
  @ApiProperty({
    description: 'Instrument ID (e.g., 15144 for SPY)',
    example: 15144,
  })
  @IsInt()
  @Type(() => Number)
  instrument_id: number;

  @ApiPropertyOptional({
    description: 'Timeframe for candles',
    enum: ['5min', '1hour', '1day'],
    default: '5min',
  })
  @IsOptional()
  @IsString()
  @IsIn(['5min', '1hour', '1day'])
  timeframe?: string = '5min';

  @ApiPropertyOptional({
    description: 'Start date in YYYY-MM-DD format',
    example: '2024-01-02',
  })
  @IsOptional()
  @IsString()
  start_date?: string;

  @ApiPropertyOptional({
    description: 'End date in YYYY-MM-DD format',
    example: '2024-01-05',
  })
  @IsOptional()
  @IsString()
  end_date?: string;
}
