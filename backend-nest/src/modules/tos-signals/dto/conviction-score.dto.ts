export class ConvictionScoreDto {
  signal_id: string;
  symbol: string;
  option_type: string;
  quality_score: number;
  direction_score: number;
  magnitude_score: number;
  regime: string;
  regime_multiplier: number;
  conviction_score: number;
  sequence_quality: number | null;
  cluster_quality: number | null;
}

export class SqueezeSignalDto {
  symbol: string;
  score: number;
  gex_estimate: number | null;
  near_strike_call_vol_ratio: number;
  oi_skew: number;
  iv_rising_with_price: boolean;
  multi_strike_vol_pressure: number;
  alert: boolean;
}

export class RegimeDto {
  regime: string;
  multiplier: number;
  source: string;
}
