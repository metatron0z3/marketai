import { Controller, Get, Post, Body } from '@nestjs/common';
import { SupportResistanceService } from './support-resistance.service';

@Controller('api/v1/support-resistance')
export class SupportResistanceController {
  constructor(private readonly supportResistanceService: SupportResistanceService) {}

  @Get()
  async getAll() {
    return this.supportResistanceService.getAll();
  }

  @Post()
  async save(@Body() data: Record<string, any>) {
    return this.supportResistanceService.save(data);
  }
}
