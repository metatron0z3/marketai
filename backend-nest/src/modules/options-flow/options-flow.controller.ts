import { Controller, Post, Query, UseGuards } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { OptionsFlowService } from './options-flow.service';
import { AuthGuard } from '../auth/auth.guard';

@ApiTags('options-flow')
@ApiBearerAuth()
@UseGuards(AuthGuard)
@Controller('api/v1/flow')
export class OptionsFlowController {
  constructor(private readonly service: OptionsFlowService) {}

  @Post('compute')
  @ApiOperation({ summary: 'Compute options flow features for a symbol and date range' })
  compute(
    @Query('symbol') symbol: string,
    @Query('start_date') startDate: string,
    @Query('end_date') endDate: string,
  ) {
    return this.service.computeFeatures(symbol, startDate, endDate);
  }
}
