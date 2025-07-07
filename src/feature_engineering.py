import pandas as pd
import numpy as np
from questdb.ingress import Sender, IngressError
import psycopg2
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional
import warnings

warnings.filterwarnings("ignore")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradingFeatureEngineer:
    """
    Feature engineering pipeline for trading data stored in QuestDB.
    Generates various types of features for market prediction models.
    """

    def __init__(
        self,
        questdb_host="localhost",
        questdb_port=8812,
        questdb_user="admin",
        questdb_password="quest",
    ):
        self.questdb_host = questdb_host
        self.questdb_port = questdb_port
        self.questdb_user = questdb_user
        self.questdb_password = questdb_password
        self.connection = None

    def connect_questdb(self):
        """Establish connection to QuestDB"""
        try:
            self.connection = psycopg2.connect(
                host=self.questdb_host,
                port=self.questdb_port,
                user=self.questdb_user,
                password=self.questdb_password,
                database="qdb",
            )
            logger.info("Connected to QuestDB successfully")
        except Exception as e:
            logger.error(f"Failed to connect to QuestDB: {e}")
            raise

    def create_feature_tables(self):
        """Create feature tables in QuestDB"""
        feature_tables = {
            "price_features": """
                CREATE TABLE IF NOT EXISTS price_features (
                    ts TIMESTAMP,
                    symbol SYMBOL,
                    price DOUBLE,
                    returns_1m DOUBLE,
                    returns_5m DOUBLE,
                    returns_15m DOUBLE,
                    returns_1h DOUBLE,
                    log_returns_1m DOUBLE,
                    log_returns_5m DOUBLE,
                    volatility_1m DOUBLE,
                    volatility_5m DOUBLE,
                    volatility_15m DOUBLE,
                    price_momentum_5m DOUBLE,
                    price_momentum_15m DOUBLE,
                    rsi_14 DOUBLE,
                    bb_upper DOUBLE,
                    bb_lower DOUBLE,
                    bb_position DOUBLE
                ) TIMESTAMP(ts) PARTITION BY DAY;
            """,
            "volume_features": """
                CREATE TABLE IF NOT EXISTS volume_features (
                    ts TIMESTAMP,
                    symbol SYMBOL,
                    volume DOUBLE,
                    vwap_1m DOUBLE,
                    vwap_5m DOUBLE,
                    vwap_15m DOUBLE,
                    volume_momentum_5m DOUBLE,
                    volume_momentum_15m DOUBLE,
                    volume_ratio_5m DOUBLE,
                    volume_ratio_15m DOUBLE,
                    price_volume_correlation_5m DOUBLE,
                    price_volume_correlation_15m DOUBLE
                ) TIMESTAMP(ts) PARTITION BY DAY;
            """,
            "microstructure_features": """
                CREATE TABLE IF NOT EXISTS microstructure_features (
                    ts TIMESTAMP,
                    symbol SYMBOL,
                    trade_size DOUBLE,
                    trade_count_1m LONG,
                    trade_count_5m LONG,
                    avg_trade_size_1m DOUBLE,
                    avg_trade_size_5m DOUBLE,
                    large_trade_ratio_1m DOUBLE,
                    large_trade_ratio_5m DOUBLE,
                    trade_intensity_1m DOUBLE,
                    trade_intensity_5m DOUBLE
                ) TIMESTAMP(ts) PARTITION BY DAY;
            """,
            "technical_features": """
                CREATE TABLE IF NOT EXISTS technical_features (
                    ts TIMESTAMP,
                    symbol SYMBOL,
                    sma_5 DOUBLE,
                    sma_10 DOUBLE,
                    sma_20 DOUBLE,
                    ema_5 DOUBLE,
                    ema_10 DOUBLE,
                    ema_20 DOUBLE,
                    macd DOUBLE,
                    macd_signal DOUBLE,
                    macd_histogram DOUBLE,
                    stoch_k DOUBLE,
                    stoch_d DOUBLE
                ) TIMESTAMP(ts) PARTITION BY DAY;
            """,
        }

        cursor = self.connection.cursor()
        for table_name, create_sql in feature_tables.items():
            try:
                cursor.execute(create_sql)
                logger.info(f"Created/verified table: {table_name}")
            except Exception as e:
                logger.error(f"Error creating table {table_name}: {e}")

        self.connection.commit()
        cursor.close()

    def load_trade_data(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> pd.DataFrame:
        """Load trade data from QuestDB for a specific symbol and time range"""
        query = """
            SELECT ts, symbol, price, size as volume
            FROM trades 
            WHERE symbol = %s 
            AND ts >= %s 
            AND ts <= %s
            ORDER BY ts
        """

        try:
            df = pd.read_sql_query(
                query, self.connection, params=[symbol, start_time, end_time]
            )
            df["ts"] = pd.to_datetime(df["ts"])
            df.set_index("ts", inplace=True)
            logger.info(f"Loaded {len(df)} trades for {symbol}")
            return df
        except Exception as e:
            logger.error(f"Error loading trade data: {e}")
            return pd.DataFrame()

    def calculate_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate price-based features"""
        features = pd.DataFrame(index=df.index)
        features["symbol"] = df["symbol"]
        features["price"] = df["price"]

        # Returns over different timeframes
        for period in ["1min", "5min", "15min", "1h"]:
            period_key = period.replace("min", "m").replace("h", "h")
            features[f"returns_{period_key}"] = df["price"].pct_change(
                periods=self._get_periods(period)
            )
            features[f"log_returns_{period_key}"] = np.log(
                df["price"] / df["price"].shift(self._get_periods(period))
            )

        # Volatility (rolling standard deviation of returns)
        for period in ["1min", "5min", "15min"]:
            period_key = period.replace("min", "m")
            window = self._get_periods(period)
            features[f"volatility_{period_key}"] = (
                features[f"returns_{period_key}"].rolling(window=window).std()
            )

        # Price momentum
        features["price_momentum_5m"] = (
            df["price"] - df["price"].shift(self._get_periods("5min"))
        ) / df["price"].shift(self._get_periods("5min"))
        features["price_momentum_15m"] = (
            df["price"] - df["price"].shift(self._get_periods("15min"))
        ) / df["price"].shift(self._get_periods("15min"))

        # RSI (Relative Strength Index)
        features["rsi_14"] = self._calculate_rsi(df["price"], 14)

        # Bollinger Bands
        sma_20 = df["price"].rolling(window=20).mean()
        std_20 = df["price"].rolling(window=20).std()
        features["bb_upper"] = sma_20 + (2 * std_20)
        features["bb_lower"] = sma_20 - (2 * std_20)
        features["bb_position"] = (df["price"] - features["bb_lower"]) / (
            features["bb_upper"] - features["bb_lower"]
        )

        return features.dropna()

    def calculate_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate volume-based features"""
        features = pd.DataFrame(index=df.index)
        features["symbol"] = df["symbol"]
        features["volume"] = df["volume"]

        # Volume-weighted average price (VWAP)
        for period in ["1min", "5min", "15min"]:
            period_key = period.replace("min", "m")
            window = self._get_periods(period)

            # Calculate cumulative volume and cumulative volume*price
            cum_volume = df["volume"].rolling(window=window).sum()
            cum_volume_price = (df["volume"] * df["price"]).rolling(window=window).sum()
            features[f"vwap_{period_key}"] = cum_volume_price / cum_volume

        # Volume momentum
        features["volume_momentum_5m"] = (
            df["volume"] - df["volume"].shift(self._get_periods("5min"))
        ) / df["volume"].shift(self._get_periods("5min"))
        features["volume_momentum_15m"] = (
            df["volume"] - df["volume"].shift(self._get_periods("15min"))
        ) / df["volume"].shift(self._get_periods("15min"))

        # Volume ratios (current volume vs average volume)
        features["volume_ratio_5m"] = (
            df["volume"] / df["volume"].rolling(window=self._get_periods("5min")).mean()
        )
        features["volume_ratio_15m"] = (
            df["volume"]
            / df["volume"].rolling(window=self._get_periods("15min")).mean()
        )

        # Price-volume correlation
        features["price_volume_correlation_5m"] = (
            df["price"].rolling(window=self._get_periods("5min")).corr(df["volume"])
        )
        features["price_volume_correlation_15m"] = (
            df["price"].rolling(window=self._get_periods("15min")).corr(df["volume"])
        )

        return features.dropna()

    def calculate_microstructure_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate microstructure features"""
        features = pd.DataFrame(index=df.index)
        features["symbol"] = df["symbol"]
        features["trade_size"] = df["volume"]

        # Trade count over different periods
        for period in ["1min", "5min"]:
            period_key = period.replace("min", "m")
            window = self._get_periods(period)
            features[f"trade_count_{period_key}"] = (
                df["volume"].rolling(window=window).count()
            )
            features[f"avg_trade_size_{period_key}"] = (
                df["volume"].rolling(window=window).mean()
            )

        # Large trade ratio (trades above 75th percentile)
        large_trade_threshold = df["volume"].quantile(0.75)
        large_trades = (df["volume"] > large_trade_threshold).astype(int)

        for period in ["1min", "5min"]:
            period_key = period.replace("min", "m")
            window = self._get_periods(period)
            features[f"large_trade_ratio_{period_key}"] = large_trades.rolling(
                window=window
            ).mean()

        # Trade intensity (trades per unit time)
        for period in ["1min", "5min"]:
            period_key = period.replace("min", "m")
            window = self._get_periods(period)
            features[f"trade_intensity_{period_key}"] = (
                features[f"trade_count_{period_key}"] / window
            )

        return features.dropna()

    def calculate_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicator features"""
        features = pd.DataFrame(index=df.index)
        features["symbol"] = df["symbol"]

        # Simple Moving Averages
        for period in [5, 10, 20]:
            features[f"sma_{period}"] = df["price"].rolling(window=period).mean()

        # Exponential Moving Averages
        for period in [5, 10, 20]:
            features[f"ema_{period}"] = df["price"].ewm(span=period).mean()

        # MACD
        ema_12 = df["price"].ewm(span=12).mean()
        ema_26 = df["price"].ewm(span=26).mean()
        features["macd"] = ema_12 - ema_26
        features["macd_signal"] = features["macd"].ewm(span=9).mean()
        features["macd_histogram"] = features["macd"] - features["macd_signal"]

        # Stochastic Oscillator
        low_14 = df["price"].rolling(window=14).min()
        high_14 = df["price"].rolling(window=14).max()
        features["stoch_k"] = 100 * (df["price"] - low_14) / (high_14 - low_14)
        features["stoch_d"] = features["stoch_k"].rolling(window=3).mean()

        return features.dropna()

    def _get_periods(self, timeframe: str) -> int:
        """Convert timeframe string to number of periods (assuming 1-second data)"""
        if timeframe == "1min":
            return 60
        elif timeframe == "5min":
            return 300
        elif timeframe == "15min":
            return 900
        elif timeframe == "1h":
            return 3600
        else:
            return 1

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def save_features_to_questdb(self, features: pd.DataFrame, table_name: str):
        """Save features to QuestDB using batch insert"""
        if features.empty:
            logger.warning(f"No features to save for {table_name}")
            return

        # Reset index to make timestamp a column
        features_to_save = features.reset_index()
        features_to_save["ts"] = features_to_save["ts"].dt.strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

        # Create insert statement
        columns = list(features_to_save.columns)
        placeholders = ", ".join(["%s"] * len(columns))
        insert_sql = (
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        )

        cursor = self.connection.cursor()
        try:
            # Convert DataFrame to list of tuples
            data_tuples = [tuple(row) for row in features_to_save.values]
            cursor.executemany(insert_sql, data_tuples)
            self.connection.commit()
            logger.info(f"Saved {len(features_to_save)} records to {table_name}")
        except Exception as e:
            logger.error(f"Error saving features to {table_name}: {e}")
            self.connection.rollback()
        finally:
            cursor.close()

    def process_features_for_symbol(
        self, symbol: str, start_time: datetime, end_time: datetime
    ):
        """Process all features for a given symbol and time range"""
        logger.info(f"Processing features for {symbol} from {start_time} to {end_time}")

        # Load trade data
        df = self.load_trade_data(symbol, start_time, end_time)
        if df.empty:
            logger.warning(f"No data found for {symbol}")
            return

        # Calculate different types of features
        price_features = self.calculate_price_features(df)
        volume_features = self.calculate_volume_features(df)
        microstructure_features = self.calculate_microstructure_features(df)
        technical_features = self.calculate_technical_features(df)

        # Save features to respective tables
        self.save_features_to_questdb(price_features, "price_features")
        self.save_features_to_questdb(volume_features, "volume_features")
        self.save_features_to_questdb(
            microstructure_features, "microstructure_features"
        )
        self.save_features_to_questdb(technical_features, "technical_features")

        logger.info(f"Feature processing completed for {symbol}")

    def run_feature_pipeline(
        self, symbols: List[str], start_time: datetime, end_time: datetime
    ):
        """Run the complete feature engineering pipeline"""
        logger.info("Starting feature engineering pipeline")

        try:
            # Connect to QuestDB
            self.connect_questdb()

            # Create feature tables
            self.create_feature_tables()

            # Process features for each symbol
            for symbol in symbols:
                self.process_features_for_symbol(symbol, start_time, end_time)

            logger.info("Feature engineering pipeline completed successfully")

        except Exception as e:
            logger.error(f"Feature engineering pipeline failed: {e}")
            raise
        finally:
            if self.connection:
                self.connection.close()
                logger.info("Database connection closed")


# Example usage
if __name__ == "__main__":
    # Initialize feature engineer
    fe = TradingFeatureEngineer()

    # Define parameters
    symbols = ["SPY", "QQQ", "TSLA"]  # Replace with your actual symbols
    start_time = datetime.now() - timedelta(days=1)
    end_time = datetime.now()

    # Run the pipeline
    fe.run_feature_pipeline(symbols, start_time, end_time)
