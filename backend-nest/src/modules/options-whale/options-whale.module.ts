import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { OptionsWhaleController } from './options-whale.controller';
import { OptionsWhaleService } from './options-whale.service';

@Module({
  imports: [HttpModule],
  controllers: [OptionsWhaleController],
  providers: [OptionsWhaleService],
})
export class OptionsWhaleModule {}
