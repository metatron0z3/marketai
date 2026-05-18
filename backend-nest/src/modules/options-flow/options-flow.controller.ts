import { Controller, Post, Query } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { OptionsFlowService } from './options-flow.service';

@ApiTags('options-flow')
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
