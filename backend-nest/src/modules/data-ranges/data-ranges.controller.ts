import { Controller, Get } from '@nestjs/common';
import { ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { DataRangesService } from './data-ranges.service';
import { DataRangesResponseDto } from './dto/data-range.dto';

@ApiTags('data-ranges')
@Controller('api/v1/data-ranges')
export class DataRangesController {
  constructor(private readonly dataRangesService: DataRangesService) {}

  @Get()
  @ApiOperation({ summary: 'Get available data ranges for all symbols and datatypes' })
  @ApiResponse({
    status: 200,
    description: 'Returns data ranges grouped by provider and datatype',
    type: DataRangesResponseDto,
  })
  async getDataRanges(): Promise<DataRangesResponseDto> {
    return this.dataRangesService.getDataRanges();
  }
}
