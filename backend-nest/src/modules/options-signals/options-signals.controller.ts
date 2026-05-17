import { Controller, Get, Query, UseGuards } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { OptionsSignalsService } from './options-signals.service';
import { AuthGuard } from '../auth/auth.guard';

@ApiTags('options-signals')
@ApiBearerAuth()
@UseGuards(AuthGuard)
@Controller('api/v1/signals')
export class OptionsSignalsController {
  constructor(private readonly service: OptionsSignalsService) {}

  @Get()
  @ApiOperation({ summary: 'Get top-ranked unusual options signals' })
  getSignals(
    @Query('n') n: number = 20,
    @Query('lookback_minutes') lookbackMinutes: number = 30,
  ) {
    return this.service.getTopSignals(n, lookbackMinutes);
  }
}
