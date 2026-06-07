import { Injectable, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { ConvictionScoreDto, RegimeDto, SqueezeSignalDto } from './dto/conviction-score.dto';
import { TosSignalDto, TosSignalQueryDto } from './dto/tos-signal.dto';

const PYTHON_BASE = process.env.PYTHON_SERVICE_URL ?? 'http://python-service:8000';
const TOS_BASE = `${PYTHON_BASE}/api/v1/tos`;

@Injectable()
export class TosSignalsService {
  private readonly logger = new Logger(TosSignalsService.name);

  constructor(private readonly http: HttpService) {}

  async getSignals(query: TosSignalQueryDto): Promise<TosSignalDto[]> {
    const params: Record<string, string | number> = {};
    if (query.symbol) params['symbol'] = query.symbol;
    if (query.min_conviction != null) params['min_conviction'] = query.min_conviction;
    if (query.limit != null) params['limit'] = query.limit;

    const { data } = await firstValueFrom(
      this.http.get<TosSignalDto[]>(`${TOS_BASE}/signals`, { params }),
    );
    return data;
  }

  async getSignal(signalId: string): Promise<TosSignalDto> {
    const { data } = await firstValueFrom(
      this.http.get<TosSignalDto>(`${TOS_BASE}/signals/${signalId}`),
    );
    return data;
  }

  async getSignalStats(symbol?: string): Promise<unknown[]> {
    const params = symbol ? { symbol } : {};
    const { data } = await firstValueFrom(
      this.http.get<unknown[]>(`${TOS_BASE}/signals/stats/summary`, { params }),
    );
    return data;
  }

  async scoreSignal(signalId: string, includeShap = false): Promise<ConvictionScoreDto> {
    const { data } = await firstValueFrom(
      this.http.get<ConvictionScoreDto>(`${TOS_BASE}/score/${signalId}`, {
        params: { include_shap: includeShap },
      }),
    );
    return data;
  }

  async getLeaderboard(
    symbol?: string,
    minConviction = 0.6,
    limit = 20,
  ): Promise<ConvictionScoreDto[]> {
    const params: Record<string, string | number> = { min_conviction: minConviction, limit };
    if (symbol) params['symbol'] = symbol;
    const { data } = await firstValueFrom(
      this.http.get<ConvictionScoreDto[]>(`${TOS_BASE}/score/leaderboard`, { params }),
    );
    return data;
  }

  async getCurrentRegime(): Promise<RegimeDto> {
    const { data } = await firstValueFrom(
      this.http.get<RegimeDto>(`${TOS_BASE}/score/regime`),
    );
    return data;
  }

  async getSqueezeScore(symbol: string): Promise<SqueezeSignalDto> {
    const { data } = await firstValueFrom(
      this.http.get<SqueezeSignalDto>(`${TOS_BASE}/score/squeeze/${symbol}`),
    );
    return data;
  }

  async getChain(symbol: string, expiry?: string, isCall?: boolean): Promise<unknown[]> {
    const params: Record<string, string | boolean> = {};
    if (expiry) params['expiry'] = expiry;
    if (isCall != null) params['is_call'] = isCall;
    const { data } = await firstValueFrom(
      this.http.get<unknown[]>(`${TOS_BASE}/chain/${symbol}`, { params }),
    );
    return data;
  }

  async getIvSurface(symbol: string): Promise<unknown[]> {
    const { data } = await firstValueFrom(
      this.http.get<unknown[]>(`${TOS_BASE}/iv-surface/${symbol}`),
    );
    return data;
  }

  async getUnusualVolume(
    symbol: string,
    days = 5,
    minVolumeRatio = 2.0,
  ): Promise<unknown[]> {
    const { data } = await firstValueFrom(
      this.http.get<unknown[]>(`${TOS_BASE}/unusual-volume/${symbol}`, {
        params: { days, min_volume_ratio: minVolumeRatio },
      }),
    );
    return data;
  }
}
