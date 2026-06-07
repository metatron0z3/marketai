import { Routes } from '@angular/router';
import { MarketDataPage } from './pages/market-data/market-data';
import { IngestPage } from './pages/ingest/ingest';
import { AnimatedChartComponent } from './animated-chart/animated-chart';
import { DataRangesPage } from './pages/data-ranges/data-ranges';
import { OptionsPage } from './pages/options/options';
import { DataOverviewPage } from './pages/data-overview/data-overview';

export const routes: Routes = [
  { path: '', redirectTo: '/data-overview', pathMatch: 'full' },
  { path: 'data-overview', component: DataOverviewPage },
  { path: 'market-data', component: MarketDataPage },
  { path: 'ingest', component: IngestPage },
  { path: 'animated-chart', component: AnimatedChartComponent },
  { path: 'data-ranges', component: DataRangesPage },
  { path: 'options', component: OptionsPage }
];
