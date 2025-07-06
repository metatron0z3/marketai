import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import os

# Configure the page
st.set_page_config(page_title="Market Data Viewer", page_icon="📈", layout="wide")

# Symbol mapping
SYMBOLS = {"SPY": 15144, "QQQ": 13340, "TSLA": 16244}

# Get QuestDB host from environment or use default
QUESTDB_HOST = os.getenv("QUESTDB_HOST", "ingestion")
QUESTDB_PORT = os.getenv("QUESTDB_PORT", "9000")
QUESTDB_URL = f"http://{QUESTDB_HOST}:{QUESTDB_PORT}/exec"


def execute_query(query):
    """Execute a query using QuestDB's HTTP interface"""
    try:
        response = requests.get(QUESTDB_URL, params={"query": query})
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            st.error(f"Query error: {result['error']}")
            return None

        return result
    except requests.exceptions.RequestException as e:
        st.error(f"Error executing query: {e}")
        st.info(f"Trying to connect to: {QUESTDB_URL}")
        return None


def get_trade_data(instrument_id, date_str=None):
    """Get trade data for a specific instrument"""

    if date_str:
        date_filter = f"AND DATE(ts_event) = '{date_str}'"
    else:
        date_filter = ""

    query = f"""
    SELECT ts_event, price, size
    FROM trades_data 
    WHERE instrument_id = {instrument_id}
    {date_filter}
    ORDER BY ts_event
    """

    result = execute_query(query)
    if not result or "dataset" not in result:
        return None

    # Convert to DataFrame
    df = pd.DataFrame(result["dataset"], columns=["ts_event", "price", "size"])
    df["ts_event"] = pd.to_datetime(df["ts_event"])
    df["price"] = pd.to_numeric(df["price"])
    df["size"] = pd.to_numeric(df["size"])

    return df


def create_ohlc_candles(df, timeframe="5Min"):
    """Create OHLC candles from trade data"""
    if df is None or df.empty:
        return None

    # Set timestamp as index
    df = df.set_index("ts_event")

    # Resample to create OHLC candles
    ohlc = df["price"].resample(timeframe).ohlc()
    volume = df["size"].resample(timeframe).sum()

    # Combine OHLC and volume
    candles = pd.concat([ohlc, volume], axis=1)
    candles.columns = ["open", "high", "low", "close", "volume"]

    # Remove rows with no data
    candles = candles.dropna()

    return candles


def create_candlestick_chart(candles, symbol):
    """Create an interactive candlestick chart"""
    if candles is None or candles.empty:
        return None

    fig = go.Figure(
        data=go.Candlestick(
            x=candles.index,
            open=candles["open"],
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            name=symbol,
            increasing_line_color="#00ff00",
            decreasing_line_color="#ff0000",
            increasing_fillcolor="rgba(0, 255, 0, 0.3)",
            decreasing_fillcolor="rgba(255, 0, 0, 0.3)",
        )
    )

    fig.update_layout(
        title=f"{symbol} - 5 Minute Candlestick Chart",
        xaxis_title="Time",
        yaxis_title="Price ($)",
        xaxis_rangeslider_visible=False,
        height=600,
        showlegend=False,
        template="plotly_dark",
    )

    # Add hover information
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>"
        + "Open: $%{open:.2f}<br>"
        + "High: $%{high:.2f}<br>"
        + "Low: $%{low:.2f}<br>"
        + "Close: $%{close:.2f}<br>"
        + "<extra></extra>"
    )

    return fig


def main():
    st.title("📈 Market Data Viewer")
    st.markdown("Interactive candlestick charts from your trade data")

    # Show connection info
    st.sidebar.info(f"Connected to: {QUESTDB_URL}")

    # Sidebar for controls
    st.sidebar.header("Chart Controls")

    # Symbol selection
    selected_symbol = st.sidebar.selectbox(
        "Select Symbol", options=list(SYMBOLS.keys()), index=0
    )

    # Date selection
    st.sidebar.subheader("Date Range")
    use_date_filter = st.sidebar.checkbox("Filter by date", value=True)

    if use_date_filter:
        selected_date = st.sidebar.date_input(
            "Select Date",
            value=datetime.date(2024, 1, 2),
            min_value=datetime.date(2024, 1, 1),
            max_value=datetime.date(2024, 12, 31),
        )
        date_str = selected_date.strftime("%Y-%m-%d")
    else:
        date_str = None

    # Get instrument ID
    instrument_id = SYMBOLS[selected_symbol]

    # Load data
    with st.spinner(f"Loading {selected_symbol} trade data..."):
        df = get_trade_data(instrument_id, date_str)

    if df is None or df.empty:
        st.error(f"No data found for {selected_symbol}")
        if date_str:
            st.info(f"Try a different date or uncheck 'Filter by date'")
        return

    # Display data info
    st.subheader("Data Summary")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Trades", len(df))

    with col2:
        st.metric(
            "Date Range",
            f"{df['ts_event'].min().strftime('%Y-%m-%d')} to {df['ts_event'].max().strftime('%Y-%m-%d')}",
        )

    with col3:
        st.metric("Price Range", f"${df['price'].min():.2f} - ${df['price'].max():.2f}")

    with col4:
        st.metric("Total Volume", f"{df['size'].sum():,}")

    # Create candles
    with st.spinner("Creating candlestick chart..."):
        candles = create_ohlc_candles(df, "5Min")

    if candles is None or candles.empty:
        st.error("Could not create candlestick data")
        return

    # Create and display chart
    fig = create_candlestick_chart(candles, selected_symbol)
    if fig:
        st.plotly_chart(fig, use_container_width=True)

    # Show candle data
    with st.expander("View Candle Data"):
        st.dataframe(candles)

    # Show raw trade data sample
    with st.expander("View Raw Trade Data (Last 100 trades)"):
        st.dataframe(df.tail(100))


if __name__ == "__main__":
    main()
