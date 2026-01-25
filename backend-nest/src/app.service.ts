import { Injectable } from '@nestjs/common';
import { QuestdbService } from './database/questdb.service';

@Injectable()
export class AppService {
  constructor(private readonly questdbService: QuestdbService) {}

  getHealth() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
    };
  }

  async getDbStatus() {
    try {
      const result = await this.questdbService.query('SELECT 1');
      return {
        status: 'success',
        message: 'Successfully connected to QuestDB',
      };
    } catch (error) {
      return {
        status: 'error',
        message: `Failed to connect to QuestDB: ${error.message}`,
      };
    }
  }
}
