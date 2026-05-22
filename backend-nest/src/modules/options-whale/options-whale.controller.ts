import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { OptionsWhaleService } from './options-whale.service';

@ApiTags('options-whale')
@Controller('api/v1/whale')
export class OptionsWhaleController {
  constructor(private readonly service: OptionsWhaleService) {}

  @Get('signals')
  @ApiOperation({ summary: 'Get top-ranked whale positioning signals (2-8 week horizon)' })
  getSignals(
    @Query('n') n: number = 20,
    @Query('lookback_days') lookbackDays: number = 5,
  ) {
    return this.service.getWhaleSignals(n, lookbackDays);
  }

  @Post('predict')
  @ApiOperation({ summary: 'Score a whale contract snapshot' })
  predict(@Body() snapshot: Record<string, any>) {
    return this.service.predictWhale(snapshot);
  }

  @Post('features/compute')
  @ApiOperation({ summary: 'Compute whale features for a symbol and date range' })
  computeFeatures(
    @Query('symbol') symbol: string,
    @Query('start_date') startDate: string,
    @Query('end_date') endDate: string,
  ) {
    return this.service.computeWhaleFeatures(symbol, startDate, endDate);
  }

  @Post('labels/generate')
  @ApiOperation({ summary: 'Generate 4-week labels for whale features' })
  generateLabels(
    @Query('symbol') symbol: string,
    @Query('start_date') startDate: string,
    @Query('end_date') endDate: string,
  ) {
    return this.service.generateWhaleLabels(symbol, startDate, endDate);
  }
}
