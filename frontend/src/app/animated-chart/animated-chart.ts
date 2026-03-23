import { Component, AfterViewInit, OnDestroy, ElementRef, ViewChild } from '@angular/core';
import { createChart, IChartApi, ISeriesApi, CandlestickSeries, Time } from 'lightweight-charts';
import { WebsocketService, WSTick } from '../core/services/websocket.service';
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
export class AnimatedChartComponent implements AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') chartContainer!: ElementRef;

  private chart!: IChartApi;
  private candlestickSeries!: ISeriesApi<'Candlestick'>;
  private wsSubscription!: Subscription;
  private candles: ChartCandle[] = []; // Accumulate candles for replay

  constructor(private websocketService: WebsocketService) {}

  ngAfterViewInit(): void {
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

    this.candlestickSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderDownColor: '#ef5350',
      borderUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      wickUpColor: '#26a69a',
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
        if (!this.candlestickSeries) {
          console.warn('Chart not ready, skipping tick');
          return;
        }
        const chartTime: Time = Math.floor(new Date(tick.timestamp).getTime() / 1000) as Time;

        const newCandle: ChartCandle = {
          time: chartTime,
          open: tick.open,
          high: tick.high,
          low: tick.low,
          close: tick.close,
        };

        // Add candle to array and use setData for historical replay
        this.candles.push(newCandle);
        this.candlestickSeries.setData(this.candles);

        // Auto-scroll to show latest candle
        this.chart.timeScale().scrollToRealTime();
      },
      error: (err: any) => console.error('WebSocket error in component:', err),
      complete: () => console.log('WebSocket stream completed in component'),
    });
  }
}
