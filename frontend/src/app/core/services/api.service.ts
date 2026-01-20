import { Injectable, Inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../app.config'; // Assuming environment.ts exports API_BASE_URL

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private apiUrl: string;

  constructor(private http: HttpClient, @Inject(API_BASE_URL) apiBaseUrl: string) {
    this.apiUrl = apiBaseUrl;
  }

  getInstruments(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/instruments`);
  }

  getMarketData(instrumentId: number, timeframe: string, startDate?: string, endDate?: string): Observable<any[]> {
    let params = new HttpParams()
      .set('instrument_id', instrumentId.toString())
      .set('timeframe', timeframe);

    if (startDate) {
      params = params.set('start_date', startDate);
    }
    if (endDate) {
      params = params.set('end_date', endDate);
    }

    return this.http.get<any[]>(`${this.apiUrl}/market-data`, { params });
  }
}
