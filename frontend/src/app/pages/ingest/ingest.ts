import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { interval, Subscription } from 'rxjs';
import { switchMap } from 'rxjs/operators';

interface IngestionJob {
  id: string;
  filename: string;
  table: string;
  status: 'uploading' | 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  recordsProcessed: number;
  totalRecords: number;
  totalFiles?: number;
  currentFile?: string;
  error?: string;
  startTime?: string;
  endTime?: string;
}

@Component({
  selector: 'app-ingest',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './ingest.html',
  styleUrl: './ingest.scss'
})
export class IngestPage implements OnInit, OnDestroy {
  availableTables = ['trades_data'];
  selectedTable: string = 'trades_data';
  selectedFile: File | null = null;
  selectedFileName: string = '';

  jobs: IngestionJob[] = [];
  isUploading: boolean = false;
  uploadProgress: number = 0;
  error: string | null = null;

  private pollSubscription: Subscription | null = null;
  private activeJobIds: Set<string> = new Set();

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.loadJobs();
    this.startPolling();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  startPolling(): void {
    // Poll every 2 seconds for active jobs
    this.pollSubscription = interval(2000).pipe(
      switchMap(() => this.apiService.getIngestionJobs())
    ).subscribe({
      next: (jobs) => {
        this.jobs = jobs;
        // Track active jobs
        this.activeJobIds.clear();
        jobs.forEach(job => {
          if (job.status === 'uploading' || job.status === 'processing' || job.status === 'pending') {
            this.activeJobIds.add(job.id);
          }
        });
      },
      error: (err) => {
        console.error('Error polling jobs:', err);
      }
    });
  }

  stopPolling(): void {
    if (this.pollSubscription) {
      this.pollSubscription.unsubscribe();
      this.pollSubscription = null;
    }
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.selectedFile = input.files[0];
      this.selectedFileName = this.selectedFile.name;
      this.error = null;

      // Validate file extension
      if (!this.selectedFileName.endsWith('.dbn.zst') &&
          !this.selectedFileName.endsWith('.zip')) {
        this.error = 'Invalid file type. Please select a .dbn.zst or .zip file';
        this.selectedFile = null;
        this.selectedFileName = '';
      }
    }
  }

  async uploadAndIngest(): Promise<void> {
    if (!this.selectedFile) {
      this.error = 'Please select a file first';
      return;
    }

    this.isUploading = true;
    this.uploadProgress = 0;
    this.error = null;

    try {
      const formData = new FormData();
      formData.append('file', this.selectedFile);
      formData.append('table', this.selectedTable);

      // Upload file - this will return quickly once upload completes
      let lastProgress = 0;
      await this.apiService.uploadAndIngest(formData, (progress) => {
        this.uploadProgress = progress;
        lastProgress = progress;
      }).toPromise();

      console.log('Upload complete, processing started in background');

      // Reset form
      this.selectedFile = null;
      this.selectedFileName = '';
      this.uploadProgress = 0;

      // The polling interval will automatically update the jobs list

    } catch (err: any) {
      this.error = err.error?.detail || 'Failed to upload file';
      console.error('Upload error:', err);
    } finally {
      this.isUploading = false;
    }
  }

  loadJobs(): void {
    this.apiService.getIngestionJobs().subscribe({
      next: (jobs) => {
        this.jobs = jobs;
      },
      error: (err) => {
        console.error('Error loading jobs:', err);
      }
    });
  }

  refreshJobs(): void {
    this.loadJobs();
  }

  getStatusClass(status: string): string {
    const classes: { [key: string]: string } = {
      'pending': 'status-pending',
      'processing': 'status-processing',
      'completed': 'status-completed',
      'failed': 'status-failed'
    };
    return classes[status] || '';
  }

  formatDuration(startTime?: string, endTime?: string): string {
    if (!startTime) return '-';

    const start = new Date(startTime);
    const end = endTime ? new Date(endTime) : new Date();
    const durationMs = end.getTime() - start.getTime();
    const seconds = Math.floor(durationMs / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  }

  formatNumber(num: number): string {
    return num.toLocaleString();
  }
}
