import { Controller, Get, Param, NotFoundException } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse, ApiParam } from '@nestjs/swagger';
import { InstrumentsService } from './instruments.service';
import { InstrumentDto } from './dto/instrument.dto';

@Controller('api/v1/instruments')
@ApiTags('instruments')
export class InstrumentsController {
  constructor(private readonly instrumentsService: InstrumentsService) {}

  @Get()
  @ApiOperation({ summary: 'Get all available instruments' })
  @ApiResponse({
    status: 200,
    description: 'List of available instruments',
    type: [InstrumentDto],
  })
  findAll(): InstrumentDto[] {
    return this.instrumentsService.findAll();
  }

  @Get(':symbol')
  @ApiOperation({ summary: 'Get instrument by symbol' })
  @ApiParam({ name: 'symbol', description: 'Instrument symbol (e.g., SPY, QQQ, TSLA)' })
  @ApiResponse({
    status: 200,
    description: 'Instrument details',
    type: InstrumentDto,
  })
  @ApiResponse({ status: 404, description: 'Instrument not found' })
  findBySymbol(@Param('symbol') symbol: string): InstrumentDto {
    const instrument = this.instrumentsService.findBySymbol(symbol);
    if (!instrument) {
      throw new NotFoundException(`Instrument ${symbol} not found`);
    }
    return instrument;
  }
}
