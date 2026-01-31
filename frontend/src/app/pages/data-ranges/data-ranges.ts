import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';

interface SymbolRange {
  symbol: string;
  instrument_id: number;
  start_date: string;
  end_date: string;
}

interface DatatypeRange {
  datatype: string;
  symbols: SymbolRange[];
}

interface DataRangesResponse {
  provider: string;
  datatypes: DatatypeRange[];
}

@Component({
  selector: 'app-data-ranges',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './data-ranges.html',
  styleUrl: './data-ranges.scss'
})
export class DataRangesPage implements OnInit {
  dataRanges: DataRangesResponse | null = null;
  loading = true;
  error: string | null = null;

  constructor(
    private apiService: ApiService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    console.log('DataRangesPage: ngOnInit called');
    this.loadDataRanges();
  }

  loadDataRanges(): void {
    console.log('DataRangesPage: loadDataRanges called');
    this.loading = true;
    this.error = null;

    this.apiService.getDataRanges().subscribe({
      next: (data) => {
        console.log('DataRangesPage: received data', data);
        this.dataRanges = data;
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('DataRangesPage: error', err);
        this.error = 'Failed to load data ranges: ' + (err.message || 'Unknown error');
        this.loading = false;
        this.cdr.detectChanges();
      }
    });
  }
}
