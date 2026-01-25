import { Injectable } from '@angular/core';
import { Observable, Subject } from 'rxjs';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';

export interface WSTick {
  timestamp: string; // Assuming string for now, will parse to Date
  instrumentId: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  isFinal: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class WebsocketService {
  private socket$!: WebSocketSubject<WSTick>;
  private messagesSubject = new Subject<WSTick>();
  public messages$ = this.messagesSubject.asObservable();

  constructor() {
    this.connect('ws://localhost:8082/ws'); // Connect to the Go streaming service
  }

  private connect(url: string): void {
    if (!this.socket$ || this.socket$.closed) {
      this.socket$ = webSocket<WSTick>(url);
      this.socket$.subscribe(
        msg => this.messagesSubject.next(msg),
        err => {
          console.error('WebSocket error:', err);
          // Attempt to reconnect on error
          setTimeout(() => this.connect(url), 5000);
        },
        () => {
          console.warn('WebSocket connection closed.');
          // Attempt to reconnect on close
          setTimeout(() => this.connect(url), 5000);
        }
      );
    }
  }

  sendMessage(msg: any): void {
    this.socket$.next(msg);
  }

  close(): void {
    this.socket$.complete();
  }
}
