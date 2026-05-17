import { Module, Global } from '@nestjs/common';
import { QuestdbService } from './questdb.service';

@Global()
@Module({
  providers: [QuestdbService],
  exports: [QuestdbService],
})
export class DatabaseModule {}
