import { ApiProperty } from '@nestjs/swagger';
import { IsString, IsDateString } from 'class-validator';

export class FlowQueryDto {
  @ApiProperty({ example: 'SPY' }) @IsString() symbol: string;
  @ApiProperty({ example: '2026-05-01' }) @IsDateString() start_date: string;
  @ApiProperty({ example: '2026-05-17' }) @IsDateString() end_date: string;
}
