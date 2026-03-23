import { Module } from '@nestjs/common';
import { DataRangesController } from './data-ranges.controller';
import { DataRangesService } from './data-ranges.service';
import { InstrumentsModule } from '../instruments/instruments.module';

@Module({
  imports: [InstrumentsModule],
  controllers: [DataRangesController],
  providers: [DataRangesService],
})
export class DataRangesModule {}
