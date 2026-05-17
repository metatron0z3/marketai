import { Controller, Get, Query, HttpException, HttpStatus } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse, ApiQuery } from '@nestjs/swagger';
import { MarketDataService } from './market-data.service';
import { MarketDataQueryDto } from './dto/market-data-query.dto';
import { OhlcvDto } from './dto/ohlcv.dto';

@Controller('api/v1/market-data')
@ApiTags('market-data')
export class MarketDataController {
  constructor(private readonly marketDataService: MarketDataService) {}

  @Get()
  @ApiOperation({ summary: 'Get aggregated OHLCV market data' })
  @ApiQuery({ name: 'instrument_id', required: true, type: Number, description: 'The instrument ID to query' })
  @ApiQuery({ name: 'timeframe', required: false, enum: ['5min', '1hour', '1day'], description: 'Aggregation timeframe' })
  @ApiQuery({ name: 'start_date', required: false, type: String, description: 'Start date (YYYY-MM-DD)' })
  @ApiQuery({ name: 'end_date', required: false, type: String, description: 'End date (YYYY-MM-DD)' })
  @ApiResponse({
    status: 200,
    description: 'OHLCV market data',
    type: [OhlcvDto],
  })
  @ApiResponse({ status: 500, description: 'Database query error' })
  async getMarketData(@Query() query: MarketDataQueryDto): Promise<OhlcvDto[]> {
    try {
      return await this.marketDataService.getMarketData(query);
    } catch (error) {
      throw new HttpException(
        `Database query error: ${error.message}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }
}
