import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { OptionsFlowController } from './options-flow.controller';
import { OptionsFlowService } from './options-flow.service';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [HttpModule, AuthModule],
  controllers: [OptionsFlowController],
  providers: [OptionsFlowService],
})
export class OptionsFlowModule {}
