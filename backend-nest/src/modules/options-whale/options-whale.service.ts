import { Injectable } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';

@Injectable()
export class OptionsWhaleService {
  private readonly pythonUrl: string;

  constructor(
    private readonly http: HttpService,
    private readonly config: ConfigService,
  ) {
    this.pythonUrl = this.config.get<string>('pythonService.url', 'http://python-service:8000');
  }

  async getWhaleSignals(n: number, lookbackDays: number): Promise<any> {
    const url = `${this.pythonUrl}/api/v1/options/whale/signals`;
    const { data } = await firstValueFrom(
      this.http.get(url, { params: { n, lookback_days: lookbackDays } }),
    );
    return data;
  }

  async predictWhale(snapshot: Record<string, any>): Promise<any> {
    const url = `${this.pythonUrl}/api/v1/options/whale/predict`;
    const { data } = await firstValueFrom(this.http.post(url, snapshot));
    return data;
  }

  async computeWhaleFeatures(symbol: string, startDate: string, endDate: string): Promise<any> {
    const url = `${this.pythonUrl}/api/v1/options/whale/features/compute`;
    const { data } = await firstValueFrom(
      this.http.post(url, null, { params: { symbol, start_date: startDate, end_date: endDate } }),
    );
    return data;
  }

  async generateWhaleLabels(symbol: string, startDate: string, endDate: string): Promise<any> {
    const url = `${this.pythonUrl}/api/v1/options/whale/labels/generate`;
    const { data } = await firstValueFrom(
      this.http.post(url, null, { params: { symbol, start_date: startDate, end_date: endDate } }),
    );
    return data;
  }
}
