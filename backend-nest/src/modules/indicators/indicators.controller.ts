import { Controller, Get, Query } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiQuery } from '@nestjs/swagger';
import { IndicatorsService } from './indicators.service';
import { IndicatorsQueryDto } from './dto/indicators-query.dto';

@Controller('api/v1/indicators')
@ApiTags('indicators')
export class IndicatorsController {
  constructor(private readonly indicatorsService: IndicatorsService) {}

  @Get('rsi')
  @ApiOperation({ summary: 'Get RSI (14-period) for an instrument' })
  async getRsi(@Query() query: IndicatorsQueryDto) {
    return this.indicatorsService.getRsi(query);
  }

  @Get('vwap')
  @ApiOperation({ summary: 'Get VWAP (Volume Weighted Average Price) for an instrument' })
  async getVwap(@Query() query: IndicatorsQueryDto) {
    return this.indicatorsService.getVwap(query);
  }

  @Get('ma200')
  @ApiOperation({ summary: 'Get 200-period Moving Average for an instrument' })
  async getMa200(@Query() query: IndicatorsQueryDto) {
    return this.indicatorsService.getMa200(query);
  }

  @Get('ma20')
  @ApiOperation({ summary: 'Get 20-period Moving Average for an instrument' })
  async getMa20(@Query() query: IndicatorsQueryDto) {
    return this.indicatorsService.getMa20(query);
  }

  @Get('ma7')
  @ApiOperation({ summary: 'Get 7-period Moving Average for an instrument' })
  async getMa7(@Query() query: IndicatorsQueryDto) {
    return this.indicatorsService.getMa7(query);
  }

  @Get('bollinger-bands')
  @ApiOperation({ summary: 'Get Bollinger Bands (20-period, 2 std dev) for an instrument' })
  async getBollingerBands(@Query() query: IndicatorsQueryDto) {
    return this.indicatorsService.getBollingerBands(query);
  }

  @Get('volume')
  @ApiOperation({ summary: 'Get per-candle volume for an instrument' })
  async getVolume(@Query() query: IndicatorsQueryDto) {
    return this.indicatorsService.getVolume(query);
  }
}
