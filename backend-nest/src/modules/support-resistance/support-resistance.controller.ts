import { Controller, Get, Post, Body } from '@nestjs/common';
import { SupportResistanceService, SupportResistanceData } from './support-resistance.service';

@Controller('api/v1/support-resistance')
export class SupportResistanceController {
  constructor(private readonly supportResistanceService: SupportResistanceService) {}

  @Get()
  async getAll(): Promise<SupportResistanceData> {
    return this.supportResistanceService.getAll();
  }

  @Post()
  async save(@Body() data: SupportResistanceData): Promise<{ success: boolean }> {
    return this.supportResistanceService.save(data);
  }
}
