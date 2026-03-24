import { Injectable, Inject } from '@angular/core';
import { HttpClient, HttpParams, HttpEventType, HttpEvent } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
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
    return this.http.get<any[]>(`${this.apiUrl}/instruments/`);
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

    return this.http.get<any[]>(`${this.apiUrl}/market-data/`, { params });
  }

  uploadAndIngest(formData: FormData, onProgress: (progress: number) => void): Observable<any> {
    return this.http.post(`${this.apiUrl}/ingest/upload`, formData, {
      reportProgress: true,
      observe: 'events'
    }).pipe(
      map((event: HttpEvent<any>) => {
        if (event.type === HttpEventType.UploadProgress) {
          const progress = event.total ? Math.round((100 * event.loaded) / event.total) : 0;
          onProgress(progress);
        } else if (event.type === HttpEventType.Response) {
          onProgress(100);
          return event.body;
        }
        return null;
      })
    );
  }

  getIngestionJobs(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/ingest/jobs`);
  }

  getIngestionJob(jobId: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/ingest/jobs/${jobId}`);
  }

  getDataRanges(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/data-ranges`);
  }

  getIndicator(name: string, instrumentId: number, timeframe: string, startDate?: string, endDate?: string): Observable<any> {
    let params = new HttpParams()
      .set('instrument_id', instrumentId.toString())
      .set('timeframe', timeframe);
    if (startDate) {
      params = params.set('start_date', startDate);
    }
    if (endDate) {
      params = params.set('end_date', endDate);
    }
    return this.http.get<any>(`${this.apiUrl}/indicators/${name}`, { params });
  }
}
