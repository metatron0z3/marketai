import { Component, Input, ElementRef, ViewChild, OnDestroy, AfterViewInit } from '@angular/core';
import * as LightweightCharts from 'lightweight-charts';

@Component({
  selector: 'app-test-render',
  imports: [],
  templateUrl: './test-render.html',
  styleUrl: './test-render.scss',
})
export class TestRender implements AfterViewInit, OnDestroy {
  @Input() marketData: any[] = [];
  @ViewChild('chartContainer', { static: false }) chartContainer!: ElementRef;

  private chart: any = null;
  private candlestickSeries: any = null;

  ngAfterViewInit(): void {
    this.createChart();
  }

  ngOnDestroy(): void {
    if (this.chart) {
      this.chart.remove();
    }
  }

  private createChart(): void {
    if (!this.chartContainer || !this.marketData || this.marketData.length === 0) {
      console.error('Chart container or market data not available');
      return;
    }

    // Create chart
    this.chart = LightweightCharts.createChart(this.chartContainer.nativeElement, {
      width: this.chartContainer.nativeElement.clientWidth,
      height: 600,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#e1e1e1' },
        horzLines: { color: '#e1e1e1' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // Add candlestick series using the v5.1 API
    const seriesOptions = {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    };
    this.candlestickSeries = this.chart.addSeries((LightweightCharts as any).CandlestickSeries, seriesOptions);

    // Transform and set data
    const chartData = this.transformData(this.marketData);
    if (this.candlestickSeries) {
      this.candlestickSeries.setData(chartData);
    }

    // Fit content
    this.chart.timeScale().fitContent();

    // Handle resize
    window.addEventListener('resize', this.handleResize);
  }

  private transformData(data: any[]): any[] {
    return data.map((item: any) => ({
      time: Math.floor(new Date(item.timestamp).getTime() / 1000),
      open: parseFloat(item.open),
      high: parseFloat(item.high),
      low: parseFloat(item.low),
      close: parseFloat(item.close),
    })).sort((a: any, b: any) => a.time - b.time);
  }

  private handleResize = (): void => {
    if (this.chart && this.chartContainer) {
      this.chart.applyOptions({
        width: this.chartContainer.nativeElement.clientWidth,
      });
    }
  };
}
