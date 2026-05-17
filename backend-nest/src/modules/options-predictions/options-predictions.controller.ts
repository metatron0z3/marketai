import { Body, Controller, Post, UseGuards } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { OptionsPredictionsService } from './options-predictions.service';
import { AuthGuard } from '../auth/auth.guard';

@ApiTags('options-predictions')
@ApiBearerAuth()
@UseGuards(AuthGuard)
@Controller('api/v1/predictions')
export class OptionsPredictionsController {
  constructor(private readonly service: OptionsPredictionsService) {}

  @Post()
  @ApiOperation({ summary: 'Score a contract snapshot for unusual volume signal' })
  predict(@Body() contract: Record<string, any>) {
    return this.service.predict(contract);
  }
}
