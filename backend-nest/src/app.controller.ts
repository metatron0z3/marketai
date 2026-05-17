import { Controller, Get } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import { AppService } from './app.service';

@Controller()
@ApiTags('health')
export class AppController {
  constructor(private readonly appService: AppService) {}

  @Get()
  @ApiOperation({ summary: 'Root endpoint' })
  @ApiResponse({ status: 200, description: 'Welcome message' })
  getRoot() {
    return { message: 'Welcome to the MarketAI NestJS Backend!' };
  }

  @Get('health')
  @ApiOperation({ summary: 'Health check endpoint' })
  @ApiResponse({ status: 200, description: 'Health status' })
  getHealth() {
    return this.appService.getHealth();
  }

  @Get('db-status')
  @ApiOperation({ summary: 'Database connection status' })
  @ApiResponse({ status: 200, description: 'Database connection status' })
  async getDbStatus() {
    return this.appService.getDbStatus();
  }
}
