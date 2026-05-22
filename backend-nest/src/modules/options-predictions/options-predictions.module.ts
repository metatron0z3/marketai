import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { OptionsPredictionsController } from './options-predictions.controller';
import { OptionsPredictionsService } from './options-predictions.service';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [HttpModule, AuthModule],
  controllers: [OptionsPredictionsController],
  providers: [OptionsPredictionsService],
})
export class OptionsPredictionsModule {}
