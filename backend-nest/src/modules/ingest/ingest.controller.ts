import {
  Controller,
  Get,
  Post,
  Param,
  Body,
  UseInterceptors,
  UploadedFile,
  ParseFilePipe,
  HttpException,
  HttpStatus,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiConsumes,
  ApiBody,
} from '@nestjs/swagger';
import { IngestService } from './ingest.service';
import { IngestJobDto, UploadResponseDto } from './dto/ingest.dto';

@Controller('api/v1/ingest')
@ApiTags('ingest')
export class IngestController {
  constructor(private readonly ingestService: IngestService) {}

  @Post('upload')
  @UseInterceptors(FileInterceptor('file'))
  @ApiOperation({ summary: 'Upload and ingest a data file' })
  @ApiConsumes('multipart/form-data')
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        file: {
          type: 'string',
          format: 'binary',
          description: 'The .dbn.zst or .zip file to upload',
        },
        table: {
          type: 'string',
          description: 'Target table name (e.g., trades_data)',
        },
      },
      required: ['file', 'table'],
    },
  })
  @ApiResponse({
    status: 200,
    description: 'Upload successful',
    type: UploadResponseDto,
  })
  @ApiResponse({ status: 400, description: 'Invalid file or table' })
  @ApiResponse({ status: 500, description: 'Upload failed' })
  async uploadAndIngest(
    @UploadedFile(
      new ParseFilePipe({
        fileIsRequired: true,
      }),
    )
    file: Express.Multer.File,
    @Body('table') table: string,
  ): Promise<UploadResponseDto> {
    // Validate file extension
    const filename = file.originalname.toLowerCase();
    if (!filename.endsWith('.dbn.zst') && !filename.endsWith('.zip')) {
      throw new HttpException(
        'File must be .dbn.zst or .zip',
        HttpStatus.BAD_REQUEST,
      );
    }

    // Validate table name
    if (table !== 'trades_data') {
      throw new HttpException(`Invalid table: ${table}`, HttpStatus.BAD_REQUEST);
    }

    return this.ingestService.uploadAndIngest(file, table);
  }

  @Get('jobs')
  @ApiOperation({ summary: 'Get all ingestion jobs' })
  @ApiResponse({
    status: 200,
    description: 'List of ingestion jobs',
    type: [IngestJobDto],
  })
  async getJobs(): Promise<IngestJobDto[]> {
    return this.ingestService.getJobs();
  }

  @Get('jobs/:jobId')
  @ApiOperation({ summary: 'Get a specific ingestion job status' })
  @ApiResponse({
    status: 200,
    description: 'Job details',
    type: IngestJobDto,
  })
  @ApiResponse({ status: 404, description: 'Job not found' })
  async getJob(@Param('jobId') jobId: string): Promise<IngestJobDto> {
    return this.ingestService.getJob(jobId);
  }
}
