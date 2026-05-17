import { Injectable } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';

@Injectable()
export class OptionsPredictionsService {
  private readonly pythonUrl: string;

  constructor(
    private readonly http: HttpService,
    private readonly config: ConfigService,
  ) {
    this.pythonUrl = this.config.get<string>('pythonServiceUrl', 'http://python-service:8000');
  }

  async predict(contract: Record<string, any>): Promise<any> {
    const url = `${this.pythonUrl}/api/v1/options/predict`;
    const { data } = await firstValueFrom(this.http.post(url, contract));
    return data;
  }
}
