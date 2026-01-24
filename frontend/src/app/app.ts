import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
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

  constructor(
    private apiService: ApiService,
    private cdr: ChangeDetectorRef
  ) {}

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
          this.cdr.detectChanges();
          this.fetchMarketData();
        }
      },
      error: (err) => {
        console.error('Error fetching instruments:', err);
        this.error = 'Failed to load instruments.';
        console.log('Error state:', this.error);
        this.cdr.detectChanges();
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
    this.cdr.detectChanges();
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
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Error fetching market data:', err);
        this.error = 'Failed to load market data.';
        this.loading = false;
        console.log('Error state:', this.error);
        console.log('Loading state:', this.loading);
        this.cdr.detectChanges();
      }
    });
  }

  onInstrumentChange(value: number): void {
    this.selectedInstrumentId = value;
    this.fetchMarketData();
  }

  onTimeframeChange(value: string): void {
    this.selectedTimeframe = value;
    this.fetchMarketData();
  }

  onStartDateChange(value: string): void {
    this.startDate = value;
    this.fetchMarketData();
  }

  onEndDateChange(value: string): void {
    this.endDate = value;
    this.fetchMarketData();
  }
}