import { Injectable, Logger, HttpException, HttpStatus } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';
import * as FormData from 'form-data';
import { IngestJobDto, UploadResponseDto } from './dto/ingest.dto';

@Injectable()
export class IngestService {
  private readonly logger = new Logger(IngestService.name);
  private readonly pythonServiceUrl: string;

  constructor(
    private readonly httpService: HttpService,
    private readonly configService: ConfigService,
  ) {
    this.pythonServiceUrl = this.configService.get('pythonService.url');
    this.logger.log(`Python service URL: ${this.pythonServiceUrl}`);
  }

  async uploadAndIngest(
    file: Express.Multer.File,
    table: string,
  ): Promise<UploadResponseDto> {
    this.logger.log(`Proxying upload: ${file.originalname} for table ${table}`);

    try {
      const formData = new FormData();
      formData.append('file', file.buffer, {
        filename: file.originalname,
        contentType: file.mimetype,
      });
      formData.append('table', table);

      const response = await firstValueFrom(
        this.httpService.post(`${this.pythonServiceUrl}/api/v1/ingest/upload`, formData, {
          headers: {
            ...formData.getHeaders(),
          },
          maxContentLength: Infinity,
          maxBodyLength: Infinity,
        }),
      );

      return response.data;
    } catch (error) {
      this.logger.error(`Upload proxy error: ${error.message}`, error.stack);
      const status = error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR;
      const message = error.response?.data?.detail || error.message;
      throw new HttpException(message, status);
    }
  }

  async getJobs(): Promise<IngestJobDto[]> {
    this.logger.debug('Fetching ingestion jobs from Python service');

    try {
      const response = await firstValueFrom(
        this.httpService.get(`${this.pythonServiceUrl}/api/v1/ingest/jobs`),
      );
      return response.data;
    } catch (error) {
      this.logger.error(`Get jobs error: ${error.message}`, error.stack);
      const status = error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR;
      const message = error.response?.data?.detail || error.message;
      throw new HttpException(message, status);
    }
  }

  async getJob(jobId: string): Promise<IngestJobDto> {
    this.logger.debug(`Fetching job ${jobId} from Python service`);

    try {
      const response = await firstValueFrom(
        this.httpService.get(`${this.pythonServiceUrl}/api/v1/ingest/jobs/${jobId}`),
      );
      return response.data;
    } catch (error) {
      this.logger.error(`Get job error: ${error.message}`, error.stack);
      const status = error.response?.status || HttpStatus.NOT_FOUND;
      const message = error.response?.data?.detail || error.message;
      throw new HttpException(message, status);
    }
  }
}
