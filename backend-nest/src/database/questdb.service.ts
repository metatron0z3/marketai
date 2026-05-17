import { Injectable, OnModuleDestroy, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Pool, QueryResult } from 'pg';

@Injectable()
export class QuestdbService implements OnModuleDestroy {
  private readonly logger = new Logger(QuestdbService.name);
  private pool: Pool;

  constructor(private configService: ConfigService) {
    const questdbConfig = this.configService.get('questdb');

    this.pool = new Pool({
      host: questdbConfig.host,
      port: questdbConfig.port,
      user: questdbConfig.user,
      password: questdbConfig.password,
      database: questdbConfig.database,
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 2000,
    });

    this.pool.on('error', (err) => {
      this.logger.error('Unexpected error on idle client', err);
    });

    this.logger.log(`QuestDB pool initialized: ${questdbConfig.host}:${questdbConfig.port}`);
  }

  async query<T = any>(sql: string, params?: any[]): Promise<T[]> {
    const client = await this.pool.connect();
    try {
      this.logger.debug(`Executing query: ${sql}`);
      const result: QueryResult = await client.query(sql, params);
      return result.rows as T[];
    } catch (error) {
      this.logger.error(`Query error: ${error.message}`, error.stack);
      throw error;
    } finally {
      client.release();
    }
  }

  async queryOne<T = any>(sql: string, params?: any[]): Promise<T | null> {
    const rows = await this.query<T>(sql, params);
    return rows.length > 0 ? rows[0] : null;
  }

  async execute(sql: string, params?: any[]): Promise<QueryResult> {
    const client = await this.pool.connect();
    try {
      this.logger.debug(`Executing: ${sql}`);
      return await client.query(sql, params);
    } catch (error) {
      this.logger.error(`Execute error: ${error.message}`, error.stack);
      throw error;
    } finally {
      client.release();
    }
  }

  async onModuleDestroy() {
    await this.pool.end();
    this.logger.log('QuestDB pool closed');
  }
}
