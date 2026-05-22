import { Injectable } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';

@Injectable()
export class OptionsSignalsService {
  private readonly pythonUrl: string;

  constructor(
    private readonly http: HttpService,
    private readonly config: ConfigService,
  ) {
    this.pythonUrl = this.config.get<string>('pythonService.url', 'http://python-service:8000');
  }

  async getTopSignals(n: number, lookbackMinutes: number): Promise<any> {
    const url = `${this.pythonUrl}/api/v1/options/signals`;
    const { data } = await firstValueFrom(
      this.http.get(url, { params: { n, lookback_minutes: lookbackMinutes } }),
    );
    return data;
  }
}
