import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class UploadResponseDto {
  @ApiProperty({ example: 'abc123-uuid', description: 'Job ID for tracking' })
  jobId: string;

  @ApiProperty({ example: 'Upload successful, processing started in background' })
  message: string;

  @ApiProperty({ example: 'processing', description: 'Job status' })
  status: string;
}

export class IngestJobDto {
  @ApiProperty({ example: 'abc123-uuid', description: 'Job ID' })
  id: string;

  @ApiProperty({ example: 'data.dbn.zst', description: 'Original filename' })
  filename: string;

  @ApiProperty({ example: 'trades_data', description: 'Target table' })
  table: string;

  @ApiProperty({ example: 'processing', description: 'Current status' })
  status: string;

  @ApiProperty({ example: 50, description: 'Progress percentage' })
  progress: number;

  @ApiProperty({ example: 100000, description: 'Records processed' })
  recordsProcessed: number;

  @ApiProperty({ example: 200000, description: 'Total records' })
  totalRecords: number;

  @ApiPropertyOptional({ example: 5, description: 'Number of files to process' })
  totalFiles?: number;

  @ApiPropertyOptional({ example: '2/5', description: 'Current file being processed' })
  currentFile?: string;

  @ApiProperty({ example: '2024-01-02T10:00:00.000Z', description: 'Start time' })
  startTime: string;

  @ApiPropertyOptional({ example: '2024-01-02T10:05:00.000Z', description: 'End time' })
  endTime?: string;

  @ApiPropertyOptional({ description: 'Error message if failed' })
  error?: string;
}
