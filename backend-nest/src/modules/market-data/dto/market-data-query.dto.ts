import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsInt, IsString, IsOptional, IsIn } from 'class-validator';
import { Type } from 'class-transformer';

export class MarketDataQueryDto {
  @ApiProperty({ example: 15144, description: 'The instrument ID to query' })
  @IsInt()
  @Type(() => Number)
  instrument_id: number;

  @ApiPropertyOptional({
    example: '5min',
    description: 'Aggregation timeframe: 5min, 1hour, or 1day',
    default: '5min',
  })
  @IsOptional()
  @IsString()
  @IsIn(['5min', '1hour', '1day'])
  timeframe?: string = '5min';

  @ApiPropertyOptional({
    example: '2024-01-02',
    description: 'Start date for filtering (YYYY-MM-DD)',
  })
  @IsOptional()
  @IsString()
  start_date?: string;

  @ApiPropertyOptional({
    example: '2024-01-02',
    description: 'End date for filtering (YYYY-MM-DD)',
  })
  @IsOptional()
  @IsString()
  end_date?: string;
}
