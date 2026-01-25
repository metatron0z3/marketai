import pandas as pd
import numpy as np
from questdb.connect import connect
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
from sklearn.metrics import accuracy_score, precision_score, recall_score
import ta  # Technical Analysis library
from datetime import datetime, timedelta

# 1. Data Retrieval from QuestDB
def fetch_data_from_questdb(symbol, start_date, end_date):
    with connect(host='localhost', port=9009) as conn:
        query = f"""
            SELECT ts, open, high, low, close, volume, {','.join(['feature_' + str(i) for i in range(1, 5)])}
            FROM trades
            WHERE symbol = '{symbol}'
            AND ts >= '{start_date}' AND ts <= '{end_date}'
            ORDER BY ts
        """
        df = pd.read_sql(query, conn)
    df['ts'] = pd.to_datetime(df['ts'])
    df.set_index('ts', inplace=True)
    return df

# 2. Data Preprocessing
def preprocess_data(df, sequence_length=60):
    # Handle missing values
    df = df.fillna(method='ffill').fillna(method='bfill')
    
    # Calculate target: 1 if next period's close price increases, 0 otherwise
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    
    # Add technical indicators (if not already in engineered features)
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['sma'] = ta.trend.SMAIndicator(df['close'], window=20).sma_indicator()
    df['volatility'] = df['close'].rolling(window=20).std()
    
    # Drop NaN values introduced by indicators
    df = df.dropna()
    
    # Normalize features
    feature_columns = ['open', 'high', 'low', 'close', 'volume', 'rsi', 'sma', 'volatility'] + \
                     ['feature_' + str(i) for i in range(1, 5)]
    scaler = MinMaxScaler()
    df[feature_columns] = scaler.fit_transform(df[feature_columns])
    
    # Create sequences for LSTM
    X, y = [], []
    for i in range(sequence_length, len(df)):
        X.append(df[feature_columns].iloc[i-sequence_length:i].values)
        y.append(df['target'].iloc[i])
    
    X = np.array(X)
    y = np.array(y)
    
    return X, y, scaler, feature_columns

# 3. Split Data for Time Series
def split_data(X, y, train_ratio=0.7, val_ratio=0.15):
    train_size = int(len(X) * train_ratio)
    val_size = int(len(X) * val_ratio)
    
    X_train = X[:train_size]
    y_train = y[:train_size]
    X_val = X[train_size:train_size+val_size]
    y_val = y[train_size:train_size+val_size]
    X_test = X[train_size+val_size:]
    y_test = y[train_size+val_size:]
    
    return X_train, y_train, X_val, y_val, X_test, y_test

# 4. Build LSTM Model
def build_model(input_shape):
    model = Sequential([
        LSTM(128, return_sequences=True, input_shape=input_shape),
        Dropout(0.2),
        LSTM(64),
        Dropout(0.2),
        Dense(32, activation='relu'),
        Dense(1, activation='sigmoid')
    ])
    model.compile(optimizer=Adam(learning_rate=0.001), loss='binary_crossentropy', metrics=['accuracy'])
    return model

# 5. Train and Evaluate Model
def train_and_evaluate(X_train, y_train, X_val, y_val, X_test, y_test, sequence_length, feature_count):
    model = build_model((sequence_length, feature_count))
    
    # Train model
    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=50,
        batch_size=32,
        verbose=1
    )
    
    # Evaluate on test set
    y_pred = (model.predict(X_test) > 0.5).astype(int)
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    
    print(f"Test Accuracy: {accuracy:.4f}")
    print(f"Test Precision: {precision:.4f}")
    print(f"Test Recall: {recall:.4f}")
    
    return model, history

# 6. Backtesting (Simplified)
def backtest_strategy(df, model, scaler, sequence_length, feature_columns):
    # Generate predictions for test period
    X, _, _, _ = preprocess_data(df, sequence_length)
    predictions = (model.predict(X) > 0.5).astype(int)
    
    # Simulate trading (buy if predict up, sell if predict down)
    df = df.iloc[sequence_length:].copy()
    df['prediction'] = predictions
    df['returns'] = df['close'].pct_change().shift(-1)
    df['strategy_returns'] = df['returns'] * df['prediction']
    
    # Calculate cumulative returns
    cumulative_returns = (1 + df['strategy_returns']).cumprod()
    sharpe_ratio = df['strategy_returns'].mean() / df['strategy_returns'].std() * np.sqrt(252 * 390)  # Intraday (390 min/day)
    
    print(f"Strategy Sharpe Ratio: {sharpe_ratio:.4f}")
    return cumulative_returns

# Main Execution
if __name__ == "__main__":
    # Parameters
    symbol = 'SPY'  # Example symbol
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    sequence_length = 60
    train_ratio, val_ratio = 0.7, 0.15
    
    # Fetch and preprocess data
    df = fetch_data_from_questdb(symbol, start_date, end_date)
    X, y, scaler, feature_columns = preprocess_data(df, sequence_length)
    
    # Split data
    X_train, y_train, X_val, y_val, X_test, y_test = split_data(X, y, train_ratio, val_ratio)
    
    # Train and evaluate model
    model, history = train_and_evaluate(X_train, y_train, X_val, y_val, X_test, y_test, sequence_length, len(feature_columns))
    
    # Backtest strategy
    cumulative_returns = backtest_strategy(df, model, scaler, sequence_length, feature_columns)
    
    print("ML Pipeline executed successfully!")