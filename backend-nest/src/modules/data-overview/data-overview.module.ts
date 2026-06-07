import { Module } from '@nestjs/common';
import { DataOverviewController } from './data-overview.controller';
import { DataOverviewService } from './data-overview.service';

@Module({
  controllers: [DataOverviewController],
  providers: [DataOverviewService],
})
export class DataOverviewModule {}
