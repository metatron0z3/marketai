import { Injectable } from '@nestjs/common';
import * as fs from 'fs';
import * as path from 'path';

export interface SupportResistanceLine {
  price: number;
  createdAt: string;
}

export interface SupportResistanceData {
  [symbol: string]: SupportResistanceLine[];
}

@Injectable()
export class SupportResistanceService {
  private readonly metadataDir = path.join(process.cwd(), 'metadata');
  private readonly filePath = path.join(this.metadataDir, 'support-resistance.json');

  constructor() {
    // Ensure metadata directory exists
    if (!fs.existsSync(this.metadataDir)) {
      fs.mkdirSync(this.metadataDir, { recursive: true });
    }
  }

  async getAll(): Promise<SupportResistanceData> {
    try {
      if (fs.existsSync(this.filePath)) {
        const content = fs.readFileSync(this.filePath, 'utf-8');
        return JSON.parse(content);
      }
      return {};
    } catch (error) {
      console.error('Error reading support-resistance file:', error);
      return {};
    }
  }

  async save(data: SupportResistanceData): Promise<{ success: boolean }> {
    try {
      fs.writeFileSync(this.filePath, JSON.stringify(data, null, 2));
      return { success: true };
    } catch (error) {
      console.error('Error writing support-resistance file:', error);
      throw error;
    }
  }
}
