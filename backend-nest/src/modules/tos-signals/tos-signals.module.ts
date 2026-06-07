import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { TosSignalsController } from './tos-signals.controller';
import { TosSignalsService } from './tos-signals.service';

@Module({
  imports: [HttpModule],
  controllers: [TosSignalsController],
  providers: [TosSignalsService],
  exports: [TosSignalsService],
})
export class TosSignalsModule {}
