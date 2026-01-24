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
import { CommonModule } from '@angular/common'; // Re-add CommonModule import
import { createChart, IChartApi, ISeriesApi, CandlestickData, UTCTimestamp } from 'lightweight-charts';

console.log('Chart.ts file loaded'); // Keep for now

@Component({
  selector: 'app-chart',
  standalone: true, // Re-add standalone: true
  imports: [CommonModule], // Re-add CommonModule to imports
  templateUrl: './chart.html',
  styleUrl: './chart.scss'
})
export class ChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  static componentLoaded = true; // Keep for now
  @Input() data: any[] = [];
  @ViewChild('chartContainer') chartContainer!: ElementRef;

  private chart: IChartApi | null = null;
  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  private resizeObserver: ResizeObserver | null = null;

  ngAfterViewInit(): void {
    if (this.chartContainer) {
      this.chart = createChart(this.chartContainer.nativeElement, {
        width: this.chartContainer.nativeElement.clientWidth,
        height: 500, // Initial height
        layout: {
          background: { color: '#ffffff' },
          textColor: '#333',
        },
        grid: {
          vertLines: {
            color: 'rgba(197, 203, 206, 0.5)',
          },
          horzLines: {
            color: 'rgba(197, 203, 206, 0.5)',
          },
        },
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
        }
      });

      console.log('Chart object after creation:', this.chart);
      console.log('Type of chart object after creation:', typeof this.chart);
      console.log('Does chart have addCandlestickSeries:', 'addCandlestickSeries' in this.chart);


      // @ts-ignore
      this.candlestickSeries = (this.chart as IChartApi).addCandlestickSeries({
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
    if (changes['data'] && this.candlestickSeries) {
      this.updateChartData();
    }
  }

  private updateChartData(): void {
    if (this.candlestickSeries && this.data && this.data.length > 0) {
      const formattedData: CandlestickData[] = this.data.map(d => ({
        time: (new Date(d.timestamp).getTime() / 1000) as UTCTimestamp,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      })).sort((a, b) => a.time - b.time); // Ensure data is sorted by time

      this.candlestickSeries.setData(formattedData);
      this.chart?.timeScale().fitContent();
    }
  }

  private setupResizeObserver(): void {
    if (this.chartContainer) {
      this.resizeObserver = new ResizeObserver(entries => {
        if (entries.length > 0 && entries[0].contentRect) {
          const { width, height } = entries[0].contentRect;
          this.chart?.applyOptions({ width, height });
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
