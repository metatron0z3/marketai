import {
  Controller,
  Get,
  Param,
  Query,
  ParseFloatPipe,
  ParseIntPipe,
  DefaultValuePipe,
  Optional,
} from '@nestjs/common';
import { TosSignalsService } from './tos-signals.service';

@Controller('api/v1/tos-signals')
export class TosSignalsController {
  constructor(private readonly service: TosSignalsService) {}

  // --- Signals ---

  @Get('signals')
  getSignals(
    @Query('symbol') symbol?: string,
    @Query('min_conviction', new DefaultValuePipe(0), ParseFloatPipe) minConviction?: number,
    @Query('limit', new DefaultValuePipe(50), ParseIntPipe) limit?: number,
  ) {
    return this.service.getSignals({ symbol, min_conviction: minConviction, limit });
  }

  @Get('signals/stats')
  getSignalStats(@Query('symbol') symbol?: string) {
    return this.service.getSignalStats(symbol);
  }

  @Get('signals/:signalId')
  getSignal(@Param('signalId') signalId: string) {
    return this.service.getSignal(signalId);
  }

  // --- Conviction scores ---

  @Get('leaderboard')
  getLeaderboard(
    @Query('symbol') symbol?: string,
    @Query('min_conviction', new DefaultValuePipe(0.6), ParseFloatPipe) minConviction?: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit?: number,
  ) {
    return this.service.getLeaderboard(symbol, minConviction, limit);
  }

  @Get('score/regime')
  getCurrentRegime() {
    return this.service.getCurrentRegime();
  }

  @Get('score/squeeze/:symbol')
  getSqueezeScore(@Param('symbol') symbol: string) {
    return this.service.getSqueezeScore(symbol);
  }

  @Get('score/:signalId')
  scoreSignal(
    @Param('signalId') signalId: string,
    @Query('include_shap', new DefaultValuePipe(false)) includeShap?: boolean,
  ) {
    return this.service.scoreSignal(signalId, includeShap as boolean);
  }

  // --- Chain and IV ---

  @Get('chain/:symbol')
  getChain(
    @Param('symbol') symbol: string,
    @Query('expiry') expiry?: string,
    @Query('is_call') isCall?: string,
  ) {
    const isCallBool = isCall == null ? undefined : isCall === 'true';
    return this.service.getChain(symbol, expiry, isCallBool);
  }

  @Get('iv-surface/:symbol')
  getIvSurface(@Param('symbol') symbol: string) {
    return this.service.getIvSurface(symbol);
  }

  @Get('unusual-volume/:symbol')
  getUnusualVolume(
    @Param('symbol') symbol: string,
    @Query('days', new DefaultValuePipe(5), ParseIntPipe) days?: number,
    @Query('min_volume_ratio', new DefaultValuePipe(2.0), ParseFloatPipe) minVolumeRatio?: number,
  ) {
    return this.service.getUnusualVolume(symbol, days, minVolumeRatio);
  }
}
