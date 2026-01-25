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

  // US Eastern Time market hours (in ET local time)
  // Pre-market: 4:00 AM - 9:30 AM ET
  // Market hours: 9:30 AM - 4:00 PM ET
  // After-hours: 4:00 PM - 8:00 PM ET
  private readonly ET_PRE_MARKET_START = 4;     // 4:00 AM ET
  private readonly ET_MARKET_OPEN = 9.5;        // 9:30 AM ET
  private readonly ET_MARKET_CLOSE = 16;        // 4:00 PM ET
  private readonly ET_AFTER_MARKET_END = 20;    // 8:00 PM ET

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
            // Format in US Eastern timezone
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

  /**
   * Get the UTC offset for US Eastern Time on a given date.
   * Returns 5 for EST (winter) or 4 for EDT (summer).
   */
  private getETOffset(dateStr: string): number {
    // Create a date at noon ET to check DST
    // DST in US: starts 2nd Sunday in March, ends 1st Sunday in November
    const date = new Date(dateStr + 'T12:00:00');
    const jan = new Date(date.getFullYear(), 0, 1);
    const jul = new Date(date.getFullYear(), 6, 1);

    // Get timezone offsets (these are in minutes, negative for US)
    const janOffset = jan.getTimezoneOffset();
    const julOffset = jul.getTimezoneOffset();
    const dateOffset = date.getTimezoneOffset();

    // If the date's offset matches the smaller offset (summer), it's DST
    // Note: This only works if the browser is in a US timezone
    // For a more robust solution, we'd need a timezone library

    // Hardcode ET DST rules for simplicity
    const year = parseInt(dateStr.split('-')[0]);
    const month = parseInt(dateStr.split('-')[1]);
    const day = parseInt(dateStr.split('-')[2]);

    // DST starts 2nd Sunday of March at 2 AM ET
    // DST ends 1st Sunday of November at 2 AM ET
    const dstStart = this.getNthSundayOfMonth(year, 3, 2); // 2nd Sunday of March
    const dstEnd = this.getNthSundayOfMonth(year, 11, 1);  // 1st Sunday of November

    const checkDate = new Date(year, month - 1, day);
    const isDST = checkDate >= dstStart && checkDate < dstEnd;

    return isDST ? 4 : 5; // EDT = UTC-4, EST = UTC-5
  }

  /**
   * Get the nth Sunday of a given month
   */
  private getNthSundayOfMonth(year: number, month: number, n: number): Date {
    const firstDay = new Date(year, month - 1, 1);
    const dayOfWeek = firstDay.getDay();
    const firstSunday = dayOfWeek === 0 ? 1 : 8 - dayOfWeek;
    const nthSunday = firstSunday + (n - 1) * 7;
    return new Date(year, month - 1, nthSunday);
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
      // Create timestamps for Eastern Time market hours
      // Use a date in ET to determine DST offset
      const etOffset = this.getETOffset(dateStr);

      // Convert ET hours to UTC timestamps
      const dayStartUTC = new Date(dateStr + 'T00:00:00Z').getTime() / 1000;

      // ET times need to be converted to UTC by adding the offset
      // If ET is UTC-5 (EST), then 9:30 AM ET = 14:30 UTC (add 5 hours)
      // If ET is UTC-4 (EDT), then 9:30 AM ET = 13:30 UTC (add 4 hours)
      const preMarketStart = (dayStartUTC + (this.ET_PRE_MARKET_START + etOffset) * 3600) as UTCTimestamp;
      const marketOpen = (dayStartUTC + (this.ET_MARKET_OPEN + etOffset) * 3600) as UTCTimestamp;
      const marketClose = (dayStartUTC + (this.ET_MARKET_CLOSE + etOffset) * 3600) as UTCTimestamp;
      const afterMarketEnd = (dayStartUTC + (this.ET_AFTER_MARKET_END + etOffset) * 3600) as UTCTimestamp;

      console.log(`Session for ${dateStr}: ET offset=${etOffset}h, ` +
        `preMarket=${new Date(preMarketStart * 1000).toISOString()}, ` +
        `open=${new Date(marketOpen * 1000).toISOString()}, ` +
        `close=${new Date(marketClose * 1000).toISOString()}`);

      return {
        date: dateStr,
        preMarketStart,
        marketOpen,
        marketClose,
        afterMarketEnd,
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

    // Get the time scale width and calculate left offset
    // The chart has a right price scale, so content area starts at left edge
    // But we need to account for any internal padding
    const timeScaleWidth = timeScale.width();
    const containerWidth = rect.width;
    // The price scale is on the right, so left offset is minimal (just chart padding)
    // The time scale width is the actual drawing area width
    const rightPriceScaleWidth = containerWidth - timeScaleWidth;

    // Debug: log first candle coordinate for comparison
    if (this.data.length > 0) {
      const firstCandleTime = (new Date(this.data[0].timestamp).getTime() / 1000) as UTCTimestamp;
      const firstCandleX = timeScale.timeToCoordinate(firstCandleTime);
      console.log(`First candle (${this.data[0].timestamp}): x=${firstCandleX}, timeScaleWidth=${timeScaleWidth}, containerWidth=${containerWidth}`);
    }

    // Draw session backgrounds and day separators
    this.daySessions.forEach((session, index) => {
      // Get X coordinates for session boundaries
      const preMarketX = timeScale.timeToCoordinate(session.preMarketStart);
      const marketOpenX = timeScale.timeToCoordinate(session.marketOpen);
      const marketCloseX = timeScale.timeToCoordinate(session.marketClose);
      const afterMarketEndX = timeScale.timeToCoordinate(session.afterMarketEnd);

      console.log(`Session ${session.date} coords: preMarket=${preMarketX}, open=${marketOpenX}, close=${marketCloseX}, afterEnd=${afterMarketEndX}`);

      // Draw pre-market background (gray)
      if (preMarketX !== null && marketOpenX !== null) {
        ctx.fillStyle = this.BG_EXTENDED;
        ctx.fillRect(preMarketX, 0, marketOpenX - preMarketX, canvas.height);
      }

      // Draw after-market background (gray)
      if (marketCloseX !== null && afterMarketEndX !== null) {
        ctx.fillStyle = this.BG_EXTENDED;
        ctx.fillRect(marketCloseX, 0, afterMarketEndX - marketCloseX, canvas.height);
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
