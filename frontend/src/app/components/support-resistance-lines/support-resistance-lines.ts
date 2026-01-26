import { Component, Input, ViewChild, ElementRef, AfterViewInit, OnChanges, SimpleChanges, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IChartApi, ISeriesApi } from 'lightweight-charts';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL } from '../../core/environment';

interface SupportResistanceLine {
  price: number;
  createdAt: string;
}

interface SupportResistanceData {
  [symbol: string]: SupportResistanceLine[];
}

@Component({
  selector: 'app-support-resistance-lines',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './support-resistance-lines.html',
  styleUrl: './support-resistance-lines.scss'
})
export class SupportResistanceLinesComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() chart: IChartApi | null = null;
  @Input() chartContainer: HTMLElement | null = null;
  @Input() candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  @Input() symbol: string = '';
  @ViewChild('supportResistanceCanvas') canvasRef!: ElementRef<HTMLCanvasElement>;

  private ctx: CanvasRenderingContext2D | null = null;
  private currentHoveredPrice: number | null = null;
  private permanentLines: SupportResistanceLine[] = [];
  private chartSubscribed = false;
  private readonly LINE_COLOR_HOVER = '#FFA500'; // Orange for hover
  private readonly LINE_COLOR_PERMANENT = '#FFA500'; // Orange for permanent too
  private readonly LABEL_BG_COLOR = 'rgba(255, 165, 0, 0.9)';
  private readonly LABEL_TEXT_COLOR = '#000000';

  constructor(private http: HttpClient) {}

  ngAfterViewInit(): void {
    if (this.canvasRef) {
      this.ctx = this.canvasRef.nativeElement.getContext('2d');
      this.setCanvasSize();
      this.loadLines();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['symbol'] && !changes['symbol'].firstChange) {
      this.loadLines();
    }
    // Subscribe to chart changes when chart becomes available
    if (changes['chart'] && this.chart && !this.chartSubscribed) {
      this.subscribeToChartChanges();
    }
  }

  ngOnDestroy(): void {
    // Cleanup happens automatically when chart is destroyed
  }

  private subscribeToChartChanges(): void {
    if (!this.chart || this.chartSubscribed) return;

    this.chartSubscribed = true;

    // Redraw lines when visible range changes (scroll/zoom)
    this.chart.timeScale().subscribeVisibleTimeRangeChange(() => {
      this.drawLines();
    });
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
    if (this.currentHoveredPrice !== null && this.symbol) {
      const newLine: SupportResistanceLine = {
        price: this.currentHoveredPrice,
        createdAt: new Date().toISOString()
      };
      this.permanentLines.push(newLine);
      this.drawLines();
      this.saveLines();
    }
  }

  public onRightClick(event: MouseEvent) {
    event.preventDefault();
    if (this.currentHoveredPrice === null || !this.symbol) return;

    // Find if there's a line close to the current hover price (within 0.5% tolerance)
    const tolerance = this.currentHoveredPrice * 0.005;
    const lineToRemove = this.permanentLines.find(
      line => Math.abs(line.price - this.currentHoveredPrice!) < tolerance
    );

    if (lineToRemove) {
      this.permanentLines = this.permanentLines.filter(line => line !== lineToRemove);
      this.drawLines();
      this.saveLines();
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

    const canvas = this.canvasRef.nativeElement;
    const width = canvas.width;
    const height = canvas.height;

    this.ctx.clearRect(0, 0, width, height);

    // Draw permanent lines
    this.permanentLines.forEach(line => {
      this.drawLine(line.price, this.LINE_COLOR_PERMANENT, true);
    });

    // Draw temporary hover line
    if (this.currentHoveredPrice !== null) {
      this.drawLine(this.currentHoveredPrice, this.LINE_COLOR_HOVER, false);
    }
  }

  private drawLine(price: number, color: string, isPermanent: boolean) {
    if (!this.ctx || !this.chart || !this.candlestickSeries) {
      return;
    }

    const y = this.candlestickSeries.priceToCoordinate(price);
    if (y === null) return;

    const canvas = this.canvasRef.nativeElement;
    const width = canvas.width;

    // Draw the horizontal line
    this.ctx.beginPath();
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 2;

    if (!isPermanent) {
      // Dashed line for hover
      this.ctx.setLineDash([5, 3]);
    } else {
      this.ctx.setLineDash([]);
    }

    this.ctx.moveTo(0, y);
    this.ctx.lineTo(width - 70, y); // Leave space for label
    this.ctx.stroke();
    this.ctx.setLineDash([]);

    // Draw price label on the right
    const priceText = price.toFixed(2);
    const labelWidth = 65;
    const labelHeight = 20;
    const labelX = width - labelWidth - 5;
    const labelY = y - labelHeight / 2;

    // Label background
    this.ctx.fillStyle = this.LABEL_BG_COLOR;
    this.ctx.fillRect(labelX, labelY, labelWidth, labelHeight);

    // Label border
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(labelX, labelY, labelWidth, labelHeight);

    // Label text
    this.ctx.fillStyle = this.LABEL_TEXT_COLOR;
    this.ctx.font = '12px Arial';
    this.ctx.textAlign = 'center';
    this.ctx.textBaseline = 'middle';
    this.ctx.fillText(priceText, labelX + labelWidth / 2, y);
  }

  private loadLines() {
    if (!this.symbol) {
      this.permanentLines = [];
      this.drawLines();
      return;
    }

    // Try to load from API first, fall back to localStorage
    this.http.get<SupportResistanceData>(`${API_BASE_URL}/support-resistance`).subscribe({
      next: (data) => {
        this.permanentLines = data[this.symbol] || [];
        this.drawLines();
      },
      error: () => {
        // Fall back to localStorage
        const stored = localStorage.getItem('support-resistance');
        if (stored) {
          try {
            const data: SupportResistanceData = JSON.parse(stored);
            this.permanentLines = data[this.symbol] || [];
          } catch {
            this.permanentLines = [];
          }
        } else {
          this.permanentLines = [];
        }
        this.drawLines();
      }
    });
  }

  private saveLines() {
    if (!this.symbol) return;

    // Load existing data, update this symbol's lines, and save
    const saveToStorage = (existingData: SupportResistanceData = {}) => {
      existingData[this.symbol] = this.permanentLines;

      // Try to save to API
      this.http.post(`${API_BASE_URL}/support-resistance`, existingData).subscribe({
        next: () => {
          console.log('Support/resistance lines saved to API');
        },
        error: () => {
          // Fall back to localStorage
          localStorage.setItem('support-resistance', JSON.stringify(existingData));
          console.log('Support/resistance lines saved to localStorage');
        }
      });
    };

    // First load existing data
    this.http.get<SupportResistanceData>(`${API_BASE_URL}/support-resistance`).subscribe({
      next: (data) => saveToStorage(data),
      error: () => {
        const stored = localStorage.getItem('support-resistance');
        const existingData = stored ? JSON.parse(stored) : {};
        saveToStorage(existingData);
      }
    });
  }

  // Public method to remove a line (for future use)
  public removeLine(price: number) {
    this.permanentLines = this.permanentLines.filter(line => line.price !== price);
    this.drawLines();
    this.saveLines();
  }
}
