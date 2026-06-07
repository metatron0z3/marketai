import { Controller, Get } from '@nestjs/common';
import { DataOverviewService } from './data-overview.service';
import { DataOverviewResponseDto } from './dto/data-overview.dto';

@Controller('api/v1/data-overview')
export class DataOverviewController {
  constructor(private readonly service: DataOverviewService) {}

  @Get()
  getOverview(): Promise<DataOverviewResponseDto> {
    return this.service.getOverview();
  }
}
