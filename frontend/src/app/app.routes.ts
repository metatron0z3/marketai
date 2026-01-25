import { Routes } from '@angular/router';
import { MarketDataPage } from './pages/market-data/market-data';
import { IngestPage } from './pages/ingest/ingest';
import { AnimatedChartComponent } from './animated-chart/animated-chart';

export const routes: Routes = [
  { path: '', redirectTo: '/market-data', pathMatch: 'full' },
  { path: 'market-data', component: MarketDataPage },
  { path: 'ingest', component: IngestPage },
  { path: 'animated-chart', component: AnimatedChartComponent }
];
