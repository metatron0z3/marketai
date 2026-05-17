import { Injectable, HttpException, HttpStatus } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';
import { IndicatorsQueryDto } from './dto/indicators-query.dto';

@Injectable()
export class IndicatorsService {
  private readonly pythonServiceUrl: string;

  constructor(
    private readonly httpService: HttpService,
    private readonly configService: ConfigService,
  ) {
    this.pythonServiceUrl = this.configService.get('pythonService.url');
  }

  private async proxyGet(path: string, query: IndicatorsQueryDto): Promise<any> {
    const params = {
      instrument_id: query.instrument_id,
      ...(query.timeframe && { timeframe: query.timeframe }),
      ...(query.start_date && { start_date: query.start_date }),
      ...(query.end_date && { end_date: query.end_date }),
    };

    try {
      const response = await firstValueFrom(
        this.httpService.get(
          `${this.pythonServiceUrl}/api/v1/indicators/${path}`,
          { params },
        ),
      );
      return response.data;
    } catch (error) {
      const status = error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR;
      const message = error.response?.data?.detail || error.message;
      throw new HttpException(message, status);
    }
  }

  getRsi(query: IndicatorsQueryDto) {
    return this.proxyGet('rsi', query);
  }

  getVwap(query: IndicatorsQueryDto) {
    return this.proxyGet('vwap', query);
  }

  getMa200(query: IndicatorsQueryDto) {
    return this.proxyGet('ma200', query);
  }

  getMa20(query: IndicatorsQueryDto) {
    return this.proxyGet('ma20', query);
  }

  getMa7(query: IndicatorsQueryDto) {
    return this.proxyGet('ma7', query);
  }

  getBollingerBands(query: IndicatorsQueryDto) {
    return this.proxyGet('bollinger-bands', query);
  }

  getVolume(query: IndicatorsQueryDto) {
    return this.proxyGet('volume', query);
  }
}
