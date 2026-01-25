import { Component, OnInit, OnDestroy, ElementRef, ViewChild } from '@angular/core';
import { createChart, IChartApi, ISeriesApi, CandlestickSeriesPartialOptions, Time } from 'lightweight-charts';
import { WebsocketService, WSTick } from '../../core/services/websocket.service';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

interface ChartCandle {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
}

@Component({
  selector: 'app-animated-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './animated-chart.html',
  styleUrl: './animated-chart.scss',
})
export class AnimatedChartComponent implements OnInit, OnDestroy {
  @ViewChild('chartContainer') chartContainer!: ElementRef;

  private chart!: IChartApi;
  private candlestickSeries!: ISeriesApi<'Candlestick'>;
  private wsSubscription!: Subscription;
  private lastCandle: ChartCandle | null = null;

  constructor(private websocketService: WebsocketService) {}

  ngOnInit(): void {
    this.initChart();
    this.subscribeToWebSocket();
  }

  ngOnDestroy(): void {
    if (this.chart) {
      this.chart.remove();
    }
    if (this.wsSubscription) {
      this.wsSubscription.unsubscribe();
    }
  }

  private initChart(): void {
    if (!this.chartContainer?.nativeElement) {
      console.error('Chart container not found!');
      return;
    }

    this.chart = createChart(this.chartContainer.nativeElement, {
      width: this.chartContainer.nativeElement.clientWidth,
      height: 600,
      layout: {
        background: { color: '#131722' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#363c4e' },
        horzLines: { color: '#363c4e' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: true,
      },
      autoSize: true, // Enable auto-sizing
    });

    this.candlestickSeries = this.chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickColor: '#d1d4dc',
    });

    new ResizeObserver(entries => {
      if (entries.length > 0 && entries[0].contentRect) {
        const newRect = entries[0].contentRect;
        this.chart.applyOptions({ width: newRect.width, height: newRect.height });
      }
    }).observe(this.chartContainer.nativeElement);
  }

  private subscribeToWebSocket(): void {
    this.wsSubscription = this.websocketService.messages$.subscribe({
      next: (tick: WSTick) => {
        const chartTime: Time = Math.floor(new Date(tick.timestamp).getTime() / 1000) as Time;

        if (tick.isFinal) {
          const newCandle: ChartCandle = {
            time: chartTime,
            open: tick.open,
            high: tick.high,
            low: tick.low,
            close: tick.close,
          };
          this.candlestickSeries.update(newCandle);
          this.lastCandle = newCandle;
        } else {
          if (this.lastCandle && this.lastCandle.time === chartTime) {
            this.lastCandle.high = Math.max(this.lastCandle.high, tick.high);
            this.lastCandle.low = Math.min(this.lastCandle.low, tick.low);
            this.lastCandle.close = tick.close;
            this.candlestickSeries.update(this.lastCandle);
          } else {
            const newCandle: ChartCandle = {
              time: chartTime,
              open: tick.open,
              high: tick.high,
              low: tick.low,
              close: tick.close,
            };
            this.candlestickSeries.update(newCandle);
            this.lastCandle = newCandle;
          }
        }
      },
      error: (err: any) => console.error('WebSocket error in component:', err),
      complete: () => console.log('WebSocket stream completed in component'),
    });
  }
}
