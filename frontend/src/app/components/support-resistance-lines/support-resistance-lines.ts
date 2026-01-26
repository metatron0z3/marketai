import { Component, Input, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IChartApi, ISeriesApi } from 'lightweight-charts';

@Component({
  selector: 'app-support-resistance-lines',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './support-resistance-lines.html',
  styleUrl: './support-resistance-lines.scss'
})
export class SupportResistanceLinesComponent implements AfterViewInit {
  @Input() chart: IChartApi | null = null;
  @Input() chartContainer: HTMLElement | null = null;
  @Input() candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  @ViewChild('supportResistanceCanvas') canvasRef!: ElementRef<HTMLCanvasElement>;

  private ctx: CanvasRenderingContext2D | null = null;
  private currentHoveredPrice: number | null = null;
  private permanentLines: number[] = [];

  ngAfterViewInit(): void {
    if (this.canvasRef) {
      this.ctx = this.canvasRef.nativeElement.getContext('2d');
      this.setCanvasSize();
    }
  }

  public onResize() {
    this.setCanvasSize();
    this.drawLines();
  }

  public onMousemove(event: MouseEvent) {
    if (!this.chart || !this.chartContainer || !this.candlestickSeries) {
      return;
    }

    const rect = this.chartContainer.getBoundingClientRect();
    const y = event.clientY - rect.top;

    const price = this.candlestickSeries.coordinateToPrice(y);

    this.currentHoveredPrice = price;
    this.drawLines();
  }

  public onMouseleave() {
    this.currentHoveredPrice = null;
    this.drawLines();
  }

  public onDoubleClick() {
    if (this.currentHoveredPrice !== null) {
      this.permanentLines.push(this.currentHoveredPrice);
      this.drawLines();
      // TODO: Save permanentLines to a JSON file
    }
  }

  private setCanvasSize() {
    if (this.chartContainer && this.canvasRef) {
      const rect = this.chartContainer.getBoundingClientRect();
      this.canvasRef.nativeElement.width = rect.width;
      this.canvasRef.nativeElement.height = rect.height;
    }
  }

  private drawLines() {
    if (!this.ctx || !this.chart || !this.candlestickSeries) {
      return;
    }

    const width = this.canvasRef.nativeElement.width;
    const height = this.canvasRef.nativeElement.height;

    this.ctx.clearRect(0, 0, width, height);

    // Draw permanent lines
    this.permanentLines.forEach(price => {
      this.drawLine(price, 'blue'); // Example color for permanent lines
    });

    // Draw temporary line
    if (this.currentHoveredPrice !== null) {
      this.drawLine(this.currentHoveredPrice, 'orange');
    }
  }

  private drawLine(price: number, color: string) {
    if (!this.ctx || !this.chart || !this.candlestickSeries) {
      return;
    }

    const y = this.candlestickSeries.priceToCoordinate(price);

    this.ctx.beginPath();
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 2;
    this.ctx.moveTo(0, y);
    this.ctx.lineTo(this.canvasRef.nativeElement.width, y);
    this.ctx.stroke();
  }
}
