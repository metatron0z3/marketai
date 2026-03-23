import { Module } from '@nestjs/common';
import { SupportResistanceController } from './support-resistance.controller';
import { SupportResistanceService } from './support-resistance.service';

@Module({
  controllers: [SupportResistanceController],
  providers: [SupportResistanceService],
})
export class SupportResistanceModule {}
