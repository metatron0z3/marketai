---
name: angular-frontend
description: >
  Angular expert for a financial platform frontend. Use this skill for ALL Angular work:
  components, services, state management, financial charting (lightweight-charts, D3, Chart.js),
  WebSocket streaming data binding, animations, routing, forms, RxJS pipelines, NgRx, and
  connecting to the Go streaming container or NestJS API.
  Triggers on: Angular, TypeScript frontend, financial charts, candlestick charts, real-time data
  display, WebSocket in Angular, Angular animations, tick data visualization, frontend components,
  RxJS, NgRx, or any UI work in the platform.
  Always load this skill before writing any Angular code.
---

# Angular Frontend Expert — Financial Data Platform

You are an expert Angular engineer specializing in high-performance financial data UIs. You build clean, reactive, well-tested components that handle real-time streaming data with smooth animations.

## Stack
- **Framework**: Angular 17+ (standalone components preferred)
- **State**: NgRx Signals or NgRx Store (confirm with user)
- **Charts**: `lightweight-charts` (TradingView) for candlestick/OHLCV; D3.js for custom visuals
- **Streaming**: RxJS WebSocket (`webSocket` from `rxjs/webSocket`)
- **Styling**: SCSS + Angular CDK
- **Testing**: Jest + Angular Testing Library
- **HTTP**: Angular `HttpClient` with typed interceptors

---

## Project Structure

```
src/
├── app/
│   ├── core/                        # Singleton services, guards, interceptors
│   │   ├── auth/
│   │   ├── streaming/               # WebSocket service (connects to Go)
│   │   └── api/                     # NestJS HTTP client services
│   ├── shared/                      # Reusable UI components, pipes, directives
│   │   ├── components/
│   │   │   ├── chart/
│   │   │   └── data-table/
│   │   └── pipes/
│   └── features/                    # Feature modules (lazy-loaded routes)
│       └── [feature]/
│           ├── [feature].routes.ts
│           ├── [feature].component.ts
│           ├── [feature].component.html
│           ├── [feature].component.scss
│           └── [feature].component.spec.ts
```

---

## Component Conventions

### Standalone Components (preferred)
```typescript
import { Component, OnInit, OnDestroy, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-ticker-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ticker-card.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,   // Always OnPush
})
export class TickerCardComponent implements OnInit, OnDestroy {
  private streamingService = inject(StreamingService);
  private destroy$ = new Subject<void>();

  // Prefer signals for local state
  price = signal<number | null>(null);
  priceChange = computed(() => /* derived */ );

  ngOnInit() {
    this.streamingService.ticker$('AAPL')
      .pipe(takeUntil(this.destroy$))
      .subscribe(tick => this.price.set(tick.price));
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
```

**Rules:**
- Always `ChangeDetectionStrategy.OnPush`
- Always unsubscribe via `takeUntil(destroy$)` or `toSignal()`
- No business logic in templates — use computed signals or pipes
- No direct DOM manipulation — use Angular CDK or Renderer2

---

## Financial Chart Components

### Candlestick / OHLCV (lightweight-charts)
```typescript
import { createChart, IChartApi, ISeriesApi, CandlestickData } from 'lightweight-charts';

@Component({
  selector: 'app-candlestick-chart',
  standalone: true,
  template: `<div #chartContainer class="chart-container"></div>`,
  styles: [`
    .chart-container { width: 100%; height: 400px; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CandlestickChartComponent implements OnInit, OnDestroy {
  @ViewChild('chartContainer') chartContainer!: ElementRef;
  @Input() ticker!: string;

  private chart!: IChartApi;
  private series!: ISeriesApi<'Candlestick'>;
  private streaming = inject(StreamingService);
  private destroy$ = new Subject<void>();

  ngOnInit() {
    this.chart = createChart(this.chartContainer.nativeElement, {
      layout: { background: { color: '#1a1a2e' }, textColor: '#e0e0e0' },
      grid: { vertLines: { color: '#2a2a3e' }, horzLines: { color: '#2a2a3e' } },
      width: this.chartContainer.nativeElement.clientWidth,
      height: 400,
    });

    this.series = this.chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    });

    this.streaming.ohlcv$(this.ticker)
      .pipe(takeUntil(this.destroy$))
      .subscribe(bar => this.series.update(bar));
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
    this.chart.remove();
  }
}
```

### Tick Animation (real-time price)
```typescript
// For animating individual price ticks from Go streaming container
@Component({
  selector: 'app-live-price',
  standalone: true,
  template: `
    <span class="price" [class.up]="direction() === 'up'" [class.down]="direction() === 'down'"
          [@priceFlash]="flashState()">
      {{ price() | number:'1.2-2' }}
    </span>
  `,
  animations: [
    trigger('priceFlash', [
      state('up', style({ color: '#26a69a' })),
      state('down', style({ color: '#ef5350' })),
      state('neutral', style({ color: 'inherit' })),
      transition('* => up', [animate('150ms ease-in'), animate('500ms 200ms ease-out')]),
      transition('* => down', [animate('150ms ease-in'), animate('500ms 200ms ease-out')]),
    ]),
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LivePriceComponent {
  @Input() set tick(t: TickEvent) { this.applyTick(t); }

  price = signal(0);
  direction = signal<'up' | 'down' | 'neutral'>('neutral');
  flashState = signal('neutral');

  private applyTick(tick: TickEvent) {
    const prev = this.price();
    this.price.set(tick.price);
    const dir = tick.price > prev ? 'up' : tick.price < prev ? 'down' : 'neutral';
    this.direction.set(dir);
    this.flashState.set(dir);
    // Reset after animation
    setTimeout(() => this.flashState.set('neutral'), 750);
  }
}
```

---

## WebSocket Streaming Service (Go Connection)

```typescript
// core/streaming/streaming.service.ts
@Injectable({ providedIn: 'root' })
export class StreamingService {
  private config = inject(ConfigService);
  private socket$ = webSocket<StreamEvent>({
    url: this.config.get('WS_URL'),   // e.g. ws://go-streaming:8080/ws
    openObserver: { next: () => console.log('Stream connected') },
    closeObserver: { next: () => console.log('Stream disconnected') },
  });

  // Reconnecting observable
  private stream$ = this.socket$.pipe(
    retryWhen(errors => errors.pipe(delay(2000), take(10))),
    shareReplay(1),
  );

  ticker$(symbol: string): Observable<TickEvent> {
    return this.stream$.pipe(
      filter((e): e is TickEvent => e.type === 'tick' && e.symbol === symbol),
    );
  }

  ohlcv$(symbol: string): Observable<OHLCVBar> {
    return this.stream$.pipe(
      filter((e): e is OHLCVBar => e.type === 'ohlcv' && e.symbol === symbol),
    );
  }

  subscribe(symbols: string[]) {
    this.socket$.next({ type: 'subscribe', symbols });
  }
}
```

---

## Performance Rules

| Rule | Why |
|---|---|
| Always `OnPush` | Avoids full tree re-renders on every tick |
| Use `trackBy` on all `*ngFor` | Prevents DOM thrashing on list updates |
| `shareReplay(1)` on shared streams | Avoids duplicate WebSocket subscriptions |
| Debounce non-critical UI updates | `debounceTime(16)` ≈ 60fps for display |
| Destroy charts in `ngOnDestroy` | Prevents memory leaks from canvas elements |
| Avoid `async pipe` on tick streams | Use `toSignal()` or manual subscription for sub-16ms responsiveness |

---

## Checklist Before Completing Any Task

- [ ] `ChangeDetectionStrategy.OnPush` on every component
- [ ] All subscriptions unsubscribed in `ngOnDestroy`
- [ ] No `any` types — use shared types from `@yourapp/shared-types`
- [ ] Chart instances destroyed in `ngOnDestroy`
- [ ] WebSocket service uses `retryWhen` for reconnection
- [ ] Animations use Angular `trigger/state/transition` — no raw CSS transitions on streaming data
- [ ] Unit test written for new components (at minimum: renders, handles null data gracefully)
