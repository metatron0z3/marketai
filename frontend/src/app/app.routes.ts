import { Routes } from '@angular/router';
import { MarketDataPage } from './pages/market-data/market-data';
import { IngestPage } from './pages/ingest/ingest';

export const routes: Routes = [
  { path: '', redirectTo: '/market-data', pathMatch: 'full' },
  { path: 'market-data', component: MarketDataPage },
  { path: 'ingest', component: IngestPage }
];
