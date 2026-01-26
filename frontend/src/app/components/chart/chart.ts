import {
  Component,
  Input,
  ViewChild,
  ElementRef,
  OnChanges,
  SimpleChanges,
  AfterViewInit,
  OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  UTCTimestamp,
  CandlestickSeries
} from 'lightweight-charts';

interface DaySession {
  date: string;
  preMarketStart: UTCTimestamp;
  marketOpen: UTCTimestamp;
  marketClose: UTCTimestamp;
  afterMarketEnd: UTCTimestamp;
}

@Component({
  selector: 'app-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './chart.html',
  styleUrl: './chart.scss'
})
export class ChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() data: any[] = [];
  @ViewChild('chartContainer') chartContainer!: ElementRef;
  @ViewChild('overlayCanvas') overlayCanvas!: ElementRef<HTMLCanvasElement>;

  private chart: IChartApi | null = null;
  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private daySessions: DaySession[] = [];

  // Session times in hours (UTC - adjust if your data is in different timezone)
  private readonly PRE_MARKET_START = 9;    // 4:00 AM ET = 9:00 UTC
  private readonly MARKET_OPEN = 14.5;      // 9:30 AM ET = 14:30 UTC
  private readonly MARKET_CLOSE = 21;       // 4:00 PM ET = 21:00 UTC
  private readonly AFTER_MARKET_END = 1;    // 8:00 PM ET = 01:00 UTC next day

  // Colors
  private readonly BG_MARKET = '#1a1a1a';           // Dark for market hours
  private readonly BG_EXTENDED = 'rgba(60, 60, 60, 0.6)';  // Gray for extended hours
  private readonly DAY_SEPARATOR = '#ffeb3b';       // Yellow dashed line

  ngAfterViewInit(): void {
    if (this.chartContainer) {
      this.chart = createChart(this.chartContainer.nativeElement, {
        width: this.chartContainer.nativeElement.clientWidth,
        height: 500,
        layout: {
          background: { color: 'transparent' },  // Transparent so overlay shows
          textColor: '#d1d4dc',
        },
        grid: {
          vertLines: {
            color: 'rgba(42, 46, 57, 0.5)',
          },
          horzLines: {
            color: 'rgba(42, 46, 57, 0.5)',
          },
        },
        localization: {
          timeFormatter: (time: number) => {
            // Convert UTC timestamp to Eastern Time for display
            const date = new Date(time * 1000);
            return date.toLocaleTimeString('en-US', {
              timeZone: 'America/New_York',
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            });
          },
        },
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
          borderColor: '#2a2e39',
          tickMarkFormatter: (time: number) => {
            const date = new Date(time * 1000);
            return date.toLocaleTimeString('en-US', {
              timeZone: 'America/New_York',
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            });
          },
        },
        rightPriceScale: {
          borderColor: '#2a2e39',
        },
        crosshair: {
          mode: 1,
          vertLine: {
            color: '#758696',
            width: 1,
            style: 2,
            labelBackgroundColor: '#2a2e39',
          },
          horzLine: {
            color: '#758696',
            labelBackgroundColor: '#2a2e39',
          },
        },
      });

      // Subscribe to visible range changes to redraw overlay
      this.chart.timeScale().subscribeVisibleTimeRangeChange(() => {
        this.drawOverlay();
      });

      // Add candlestick series
      this.candlestickSeries = this.chart.addSeries(CandlestickSeries, {
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderDownColor: '#ef5350',
        borderUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        wickUpColor: '#26a69a',
      });

      this.updateChartData();
      this.setupResizeObserver();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['data'] && this.chart) {
      this.updateChartData();
    }
  }

  private isWeekday(date: Date): boolean {
    const day = date.getUTCDay();
    return day !== 0 && day !== 6;
  }

  private updateChartData(): void {
    if (!this.candlestickSeries || !this.chart || !this.data || this.data.length === 0) {
      return;
    }

    // Filter to weekdays only
    const filteredData = this.data.filter(d => {
      const date = new Date(d.timestamp);
      return this.isWeekday(date);
    });

    if (filteredData.length === 0) {
      console.log('No data after filtering for weekdays');
      return;
    }

    // Format candlestick data and collect unique dates
    const formattedData: CandlestickData<UTCTimestamp>[] = [];
    const uniqueDates = new Set<string>();

    filteredData.forEach(d => {
      const timestamp = new Date(d.timestamp);
      const time = (timestamp.getTime() / 1000) as UTCTimestamp;
      const dateStr = timestamp.toISOString().split('T')[0];
      uniqueDates.add(dateStr);

      formattedData.push({
        time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      });
    });

    // Sort by time
    formattedData.sort((a, b) => a.time - b.time);

    // Build day sessions for overlay
    this.daySessions = Array.from(uniqueDates).sort().map(dateStr => {
      const dayStart = new Date(dateStr + 'T00:00:00Z');
      return {
        date: dateStr,
        preMarketStart: (dayStart.getTime() / 1000 + this.PRE_MARKET_START * 3600) as UTCTimestamp,
        marketOpen: (dayStart.getTime() / 1000 + this.MARKET_OPEN * 3600) as UTCTimestamp,
        marketClose: (dayStart.getTime() / 1000 + this.MARKET_CLOSE * 3600) as UTCTimestamp,
        afterMarketEnd: (dayStart.getTime() / 1000 + 24 * 3600) as UTCTimestamp, // End of day
      };
    });

    // Set candlestick data
    this.candlestickSeries.setData(formattedData);
    this.chart.timeScale().fitContent();

    // Draw the overlay after a short delay to let chart render
    setTimeout(() => this.drawOverlay(), 100);

    console.log(`Chart updated: ${formattedData.length} candles, ${this.daySessions.length} days`);
  }

  private drawOverlay(): void {
    if (!this.overlayCanvas || !this.chart || this.daySessions.length === 0) {
      return;
    }

    const canvas = this.overlayCanvas.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size to match container
    const rect = this.chartContainer.nativeElement.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Fill with market hours background first
    ctx.fillStyle = this.BG_MARKET;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const timeScale = this.chart.timeScale();

    // Draw session backgrounds and day separators
    this.daySessions.forEach((session, index) => {
      // Get X coordinates for session boundaries
      const preMarketX = timeScale.timeToCoordinate(session.preMarketStart);
      const marketOpenX = timeScale.timeToCoordinate(session.marketOpen);
      const marketCloseX = timeScale.timeToCoordinate(session.marketClose);
      const afterMarketEndX = timeScale.timeToCoordinate(session.afterMarketEnd);

      // Draw pre-market background (gray)
      // Use left edge (0) if preMarketX is null/off-screen
      const preMarketStart = preMarketX !== null && preMarketX >= 0 ? preMarketX : 0;
      if (marketOpenX !== null && marketOpenX > preMarketStart) {
        ctx.fillStyle = this.BG_EXTENDED;
        ctx.fillRect(preMarketStart, 0, marketOpenX - preMarketStart, canvas.height);
      }

      // Draw after-market background (gray)
      // Use right edge of canvas if afterMarketEndX is null/off-screen
      if (marketCloseX !== null) {
        // Find the end point: either afterMarketEndX, next day's preMarketX, or canvas edge
        let afterMarketEndCoord: number | null = afterMarketEndX;
        if (afterMarketEndCoord === null) {
          // Check if there's a next day session
          const nextSession = this.daySessions[index + 1];
          if (nextSession) {
            afterMarketEndCoord = timeScale.timeToCoordinate(nextSession.preMarketStart);
          }
        }
        // If still null, use canvas width as fallback
        const afterMarketEndFinal = afterMarketEndCoord !== null ? afterMarketEndCoord : canvas.width;
        if (afterMarketEndFinal > marketCloseX) {
          ctx.fillStyle = this.BG_EXTENDED;
          ctx.fillRect(marketCloseX, 0, afterMarketEndFinal - marketCloseX, canvas.height);
        }
      }

      // Draw day separator line (dashed yellow) at the start of each day except first
      if (index > 0 && preMarketX !== null) {
        ctx.beginPath();
        ctx.strokeStyle = this.DAY_SEPARATOR;
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 5]);
        ctx.moveTo(preMarketX, 0);
        ctx.lineTo(preMarketX, canvas.height);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });
  }

  private setupResizeObserver(): void {
    if (this.chartContainer) {
      this.resizeObserver = new ResizeObserver(entries => {
        if (entries.length > 0 && entries[0].contentRect) {
          const { width } = entries[0].contentRect;
          this.chart?.applyOptions({ width, height: 500 });
          this.drawOverlay();
        }
      });
      this.resizeObserver.observe(this.chartContainer.nativeElement);
    }
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.chart?.remove();
  }
}
