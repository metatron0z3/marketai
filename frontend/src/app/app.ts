import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterOutlet } from '@angular/router';
import { ApiService } from './core/services/api.service';
import { TestRender } from './components/test-render/test-render'; // Corrected import

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterOutlet, TestRender], // Corrected usage
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
    console.log('Fetching instruments...');
    this.apiService.getInstruments().subscribe({
      next: (data) => {
        this.instruments = data;
        console.log('Instruments fetched:', this.instruments);
        if (this.instruments.length > 0) {
          this.selectedInstrumentId = this.instruments[0].id;
          console.log('Selected instrument ID:', this.selectedInstrumentId);
          this.fetchMarketData();
        }
      },
      error: (err) => {
        console.error('Error fetching instruments:', err);
        this.error = 'Failed to load instruments.';
        console.log('Error state:', this.error);
      }
    });
  }

  fetchMarketData(): void {
    if (!this.selectedInstrumentId) {
      console.log('No instrument selected, skipping market data fetch.');
      return;
    }
    this.loading = true;
    this.error = null;
    console.log('Fetching market data for instrument:', this.selectedInstrumentId, 'timeframe:', this.selectedTimeframe);

    this.apiService.getMarketData(
      this.selectedInstrumentId,
      this.selectedTimeframe,
      this.startDate || undefined,
      this.endDate || undefined
    ).subscribe({
      next: (data) => {
        this.marketData = data;
        this.loading = false;
        console.log('Market data fetched:', this.marketData);
        console.log('Loading state:', this.loading);
        console.log('Chart render conditions - loading:', this.loading, 'error:', this.error, 'marketData.length:', this.marketData.length);
      },
      error: (err) => {
        console.error('Error fetching market data:', err);
        this.error = 'Failed to load market data.';
        this.loading = false;
        console.log('Error state:', this.error);
        console.log('Loading state:', this.loading);
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