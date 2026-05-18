import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-options',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './options.html',
  styleUrl: './options.scss',
})
export class OptionsPage implements OnInit {
  activeTab: 'flow' | 'whale' = 'flow';

  flowN = 20;
  flowLookbackMinutes = 30;
  flowSignals: any[] = [];
  flowLoading = false;
  flowError: string | null = null;

  whaleN = 20;
  whaleLookbackDays = 5;
  whaleSignals: any[] = [];
  whaleLoading = false;
  whaleError: string | null = null;

  constructor(private api: ApiService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.refreshFlow();
    this.refreshWhale();
  }

  setTab(tab: 'flow' | 'whale'): void {
    this.activeTab = tab;
  }

  refreshFlow(): void {
    this.flowLoading = true;
    this.flowError = null;
    this.api.getOptionsSignals(this.flowN, this.flowLookbackMinutes).subscribe({
      next: (res) => {
        this.flowSignals = res?.signals ?? [];
        this.flowLoading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.flowError = 'Could not load signals. Check that the Python service is running.';
        this.flowLoading = false;
        this.cdr.detectChanges();
      },
    });
  }

  refreshWhale(): void {
    this.whaleLoading = true;
    this.whaleError = null;
    this.api.getWhaleSignals(this.whaleN, this.whaleLookbackDays).subscribe({
      next: (res) => {
        this.whaleSignals = res?.signals ?? [];
        this.whaleLoading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.whaleError = 'Could not load whale signals. Check that the Python service is running.';
        this.whaleLoading = false;
        this.cdr.detectChanges();
      },
    });
  }

  getScoreClass(score: number): string {
    if (score >= 0.7) return 'score-high';
    if (score >= 0.4) return 'score-medium';
    return 'score-low';
  }

  formatScore(score: number): string {
    return (score ?? 0).toFixed(2);
  }

  formatPct(v: number): string {
    return ((v ?? 0) * 100).toFixed(0) + '%';
  }

  formatPremium(v: number): string {
    if (!v) return '$0';
    if (v >= 1_000_000) return '$' + (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000) return '$' + (v / 1_000).toFixed(0) + 'K';
    return '$' + v.toFixed(0);
  }

  formatExp(exp: any): string {
    if (!exp) return '-';
    const d = new Date(exp);
    return d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' });
  }
}
