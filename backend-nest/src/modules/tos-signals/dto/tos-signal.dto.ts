export class TosSignalDto {
  signal_id: string;
  symbol: string;
  detected_at: string;
  is_call: boolean;
  option_type: string;
  strike: number;
  days_to_expiry: number;
  premium_total: number;
  volume_ratio_20d: number;
  vol_oi_ratio: number;
  otm_pct: number;
  is_sweep: boolean;
  conviction_score: number;
  quality_score: number;
  direction_score: number;
  magnitude_score: number;
  regime: string | null;
  underlying_return_1d_fwd: number | null;
  underlying_return_5d_fwd: number | null;
  direction_correct_5d: number | null;
}

export class TosSignalQueryDto {
  symbol?: string;
  min_conviction?: number;
  limit?: number;
}
