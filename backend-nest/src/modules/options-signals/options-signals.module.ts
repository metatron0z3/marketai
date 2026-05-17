import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { OptionsSignalsController } from './options-signals.controller';
import { OptionsSignalsService } from './options-signals.service';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [HttpModule, AuthModule],
  controllers: [OptionsSignalsController],
  providers: [OptionsSignalsService],
})
export class OptionsSignalsModule {}
