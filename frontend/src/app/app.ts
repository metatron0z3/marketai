import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterOutlet } from '@angular/router';
import { ApiService } from './core/services/api.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit {
  instruments: any[] = [];
  selectedInstrumentId: number | null = null;
  timeframes: string[] = ['5min', '1hour', '1day'];
  selectedTimeframe: string = '5min';
  startDate: string | null = null;
  endDate: string | null = null;
  marketData: any[] = [];
  loading: boolean = false;
  error: string | null = null;

  constructor(private apiService: ApiService) {} // Inject ApiService

  ngOnInit(): void {
    this.fetchInstruments();
  }

  fetchInstruments(): void {
    this.apiService.getInstruments().subscribe({
      next: (data) => {
        this.instruments = data;
        if (this.instruments.length > 0) {
          this.selectedInstrumentId = this.instruments[0].id;
          this.fetchMarketData();
        }
      },
      error: (err) => {
        console.error('Error fetching instruments:', err);
        this.error = 'Failed to load instruments.';
      }
    });
  }

  fetchMarketData(): void {
    if (!this.selectedInstrumentId) {
      return;
    }
    this.loading = true;
    this.error = null;

    this.apiService.getMarketData(
      this.selectedInstrumentId,
      this.selectedTimeframe,
      this.startDate || undefined,
      this.endDate || undefined
    ).subscribe({
      next: (data) => {
        this.marketData = data;
        this.loading = false;
      },
      error: (err) => {
        console.error('Error fetching market data:', err);
        this.error = 'Failed to load market data.';
        this.loading = false;
      }
    });
  }

  onInstrumentChange(event: Event): void {
    const target = event.target as HTMLSelectElement;
    this.selectedInstrumentId = Number(target.value);
    this.fetchMarketData();
  }

  onTimeframeChange(event: Event): void {
    const target = event.target as HTMLSelectElement;
    this.selectedTimeframe = target.value;
    this.fetchMarketData();
  }

  onStartDateChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    this.startDate = target.value;
    this.fetchMarketData();
  }

  onEndDateChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    this.endDate = target.value;
    this.fetchMarketData();
  }
}
