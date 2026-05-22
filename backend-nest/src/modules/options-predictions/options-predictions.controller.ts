import { Body, Controller, Post } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { OptionsPredictionsService } from './options-predictions.service';

@ApiTags('options-predictions')
@Controller('api/v1/predictions')
export class OptionsPredictionsController {
  constructor(private readonly service: OptionsPredictionsService) {}

  @Post()
  @ApiOperation({ summary: 'Score a contract snapshot for unusual volume signal' })
  predict(@Body() contract: Record<string, any>) {
    return this.service.predict(contract);
  }
}
