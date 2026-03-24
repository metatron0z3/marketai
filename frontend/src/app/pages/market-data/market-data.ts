import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { ChartComponent } from '../../components/chart/chart';

@Component({
  selector: 'app-market-data',
  standalone: true,
  imports: [CommonModule, FormsModule, ChartComponent],
  templateUrl: './market-data.html',
  styleUrl: './market-data.scss'
})
export class MarketDataPage implements OnInit {
  instruments: any[] = [];
  selectedInstrumentId: number | null = null;
  timeframes: string[] = ['5min', '1hour', '1day'];
  selectedTimeframe: string = '5min';
  startDate: string = '';
  endDate: string = '';
  marketData: any[] = [];
  loading: boolean = false;
  error: string | null = null;
  supportResistanceEnabled: boolean = false;

  // Indicator toggle state
  indicators: { [key: string]: boolean } = {
    rsi: false,
    vwap: false,
    ma200: false,
    ma20: false,
    ma7: false,
    bollingerBands: false,
    volume: false
  };
  indicatorData: { [key: string]: any } = {};

  constructor(
    private apiService: ApiService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    // Set default date range to available data (Jan 2024)
    this.startDate = '2024-01-02';
    this.endDate = '2024-01-03';

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
          // Don't auto-fetch on load, wait for user to click Pull
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

    const startDateParam = this.startDate || undefined;
    const endDateParam = this.endDate || undefined;

    console.log('Fetching market data:', {
      instrument: this.selectedInstrumentId,
      timeframe: this.selectedTimeframe,
      startDate: startDateParam,
      endDate: endDateParam
    });

    this.apiService.getMarketData(
      this.selectedInstrumentId,
      this.selectedTimeframe,
      startDateParam,
      endDateParam
    ).subscribe({
      next: (data) => {
        this.marketData = data;
        this.loading = false;
        console.log('Market data fetched:', this.marketData.length, 'records');
        console.log('Date range in data:',
          data.length > 0 ? {
            first: data[0]?.timestamp,
            last: data[data.length - 1]?.timestamp
          } : 'No data');

        // Fetch enabled indicators
        for (const [name, enabled] of Object.entries(this.indicators)) {
          if (enabled) {
            this.fetchIndicator(name);
          }
        }

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

  onPullData(): void {
    console.log('Pull button clicked - fetching data with current selections');
    this.fetchMarketData();
  }

  getSelectedSymbol(): string {
    const instrument = this.instruments.find(i => i.id === this.selectedInstrumentId);
    return instrument ? instrument.symbol : '';
  }

  formatDateRange(): string {
    if (!this.startDate && !this.endDate) {
      return 'All available data';
    }

    const start = this.startDate || 'Beginning';
    const end = this.endDate || 'Present';

    return `${start} to ${end}`;
  }

  toggleSupportResistance(): void {
    this.supportResistanceEnabled = !this.supportResistanceEnabled;
  }

  toggleIndicator(name: string): void {
    this.indicators[name] = !this.indicators[name];
    // If toggled on and market data is already loaded, fetch immediately
    if (this.indicators[name] && this.marketData.length > 0) {
      this.fetchIndicator(name);
    }
  }

  private fetchIndicator(name: string): void {
    if (!this.selectedInstrumentId) {
      return;
    }
    // Convert 'bollingerBands' to 'bollinger-bands' for API
    const endpoint = name === 'bollingerBands' ? 'bollinger-bands' : name;

    this.apiService.getIndicator(
      endpoint,
      this.selectedInstrumentId,
      this.selectedTimeframe,
      this.startDate || undefined,
      this.endDate || undefined
    ).subscribe({
      next: (data) => {
        this.indicatorData = { ...this.indicatorData, [name]: data };
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error(`Failed to fetch ${name}:`, err);
      }
    });
  }
}
