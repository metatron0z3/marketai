import { Injectable } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';

@Injectable()
export class OptionsFlowService {
  private readonly pythonUrl: string;

  constructor(
    private readonly http: HttpService,
    private readonly config: ConfigService,
  ) {
    this.pythonUrl = this.config.get<string>('pythonService.url', 'http://python-service:8000');
  }

  async computeFeatures(symbol: string, startDate: string, endDate: string): Promise<any> {
    const url = `${this.pythonUrl}/api/v1/options/features/compute`;
    const { data } = await firstValueFrom(
      this.http.post(url, null, { params: { symbol, start_date: startDate, end_date: endDate } }),
    );
    return data;
  }
}
