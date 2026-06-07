import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { DatabaseModule } from './database/database.module';
import { InstrumentsModule } from './modules/instruments/instruments.module';
import { MarketDataModule } from './modules/market-data/market-data.module';
import { IngestModule } from './modules/ingest/ingest.module';
import { IndicatorsModule } from './modules/indicators/indicators.module';
import { SupportResistanceModule } from './modules/support-resistance/support-resistance.module';
import { DataRangesModule } from './modules/data-ranges/data-ranges.module';
import { DataOverviewModule } from './modules/data-overview/data-overview.module';
import { AuthModule } from './modules/auth/auth.module';
import { OptionsSignalsModule } from './modules/options-signals/options-signals.module';
import { OptionsFlowModule } from './modules/options-flow/options-flow.module';
import { OptionsPredictionsModule } from './modules/options-predictions/options-predictions.module';
import { OptionsWhaleModule } from './modules/options-whale/options-whale.module';
import { TosSignalsModule } from './modules/tos-signals/tos-signals.module';
import configuration from './config/configuration';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      load: [configuration],
    }),
    DatabaseModule,
    InstrumentsModule,
    MarketDataModule,
    IngestModule,
    IndicatorsModule,
    SupportResistanceModule,
    DataRangesModule,
    DataOverviewModule,
    AuthModule,
    OptionsSignalsModule,
    OptionsFlowModule,
    OptionsPredictionsModule,
    OptionsWhaleModule,
    TosSignalsModule,
  ],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
