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

  // Batch upload state
  selectedFiles: File[] = [];
  totalSize: number = 0;
  isProcessing: boolean = false;
  currentFileIndex: number = 0;
  currentFileName: string = '';
  uploadProgress: number = 0;
  completedFiles: number = 0;
  error: string | null = null;

  jobs: IngestionJob[] = [];
  private pollSubscription: Subscription | null = null;

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.loadJobs();
    this.startPolling();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  startPolling(): void {
    this.pollSubscription = interval(2000).pipe(
      switchMap(() => this.apiService.getIngestionJobs())
    ).subscribe({
      next: (jobs) => {
        this.jobs = jobs;
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

  onFolderSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      // Filter for .dbn.zst files only
      const allFiles = Array.from(input.files);
      this.selectedFiles = allFiles.filter(file => file.name.endsWith('.dbn.zst'));

      // Sort by filename for consistent ordering
      this.selectedFiles.sort((a, b) => a.name.localeCompare(b.name));

      // Calculate total size
      this.totalSize = this.selectedFiles.reduce((sum, file) => sum + file.size, 0);

      this.error = null;

      if (this.selectedFiles.length === 0) {
        this.error = 'No .dbn.zst files found in the selected folder';
      } else {
        console.log(`Selected ${this.selectedFiles.length} .dbn.zst files (${this.formatBytes(this.totalSize)})`);
      }
    }
  }

  clearSelection(): void {
    this.selectedFiles = [];
    this.totalSize = 0;
    this.error = null;
    // Reset the file input
    const input = document.getElementById('folder-input') as HTMLInputElement;
    if (input) {
      input.value = '';
    }
  }

  async startBatchUpload(): Promise<void> {
    if (this.selectedFiles.length === 0) {
      this.error = 'No files selected';
      return;
    }

    this.isProcessing = true;
    this.completedFiles = 0;
    this.error = null;

    for (let i = 0; i < this.selectedFiles.length; i++) {
      const file = this.selectedFiles[i];
      this.currentFileIndex = i;
      this.currentFileName = file.name;
      this.uploadProgress = 0;

      try {
        await this.uploadSingleFile(file);
        this.completedFiles++;
        console.log(`Completed ${this.completedFiles}/${this.selectedFiles.length}: ${file.name}`);
      } catch (err: any) {
        console.error(`Failed to upload ${file.name}:`, err);
        this.error = `Failed on ${file.name}: ${err.error?.detail || err.message || 'Unknown error'}`;
        // Continue with next file instead of stopping entirely
        this.completedFiles++;
      }
    }

    this.isProcessing = false;
    this.currentFileName = '';
    this.uploadProgress = 0;

    if (!this.error) {
      console.log('Batch upload complete!');
    }
  }

  private uploadSingleFile(file: File): Promise<void> {
    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('table', this.selectedTable);

      this.apiService.uploadAndIngest(formData, (progress) => {
        this.uploadProgress = progress;
      }).subscribe({
        next: (result) => {
          if (result !== null) {
            // Response received
            resolve();
          }
        },
        error: (err) => {
          reject(err);
        },
        complete: () => {
          resolve();
        }
      });
    });
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

  formatBytes(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
}
