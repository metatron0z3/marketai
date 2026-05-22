import { ApiProperty } from '@nestjs/swagger';

export class SignalResponseDto {
  @ApiProperty() ts_event: string;
  @ApiProperty() symbol: string;
  @ApiProperty() strike: number;
  @ApiProperty() expiration: string;
  @ApiProperty() put_call: string;
  @ApiProperty() signal_score: number;
  @ApiProperty() model_loaded: boolean;
  @ApiProperty() scored_at: string;
}
