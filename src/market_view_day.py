import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import psycopg2

# Page configuration
st.set_page_config(page_title="Market View", layout="wide")

# Initialize session state for tracking changes
if "prev_instrument_id" not in st.session_state:
    st.session_state.prev_instrument_id = None
if "prev_timeframe" not in st.session_state:
    st.session_state.prev_timeframe = None


# Database connection function
def get_db_connection():
    """Create database connection to QuestDB"""
    import os

    # Use environment variable or default to 'questdb' (Docker service name)
    db_host = os.getenv("QUESTDB_HOST", "questdb")

    conn = psycopg2.connect(
        host=db_host, port=8812, database="questdb", user="admin", password="quest"
    )
    return conn


# Data fetching function with caching
@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_market_data(instrument_id, timeframe, start_date=None, end_date=None):
    """
    Fetch market data from QuestDB based on instrument and timeframe

    Args:
        instrument_id: The instrument/symbol to query
        timeframe: '5min', '1hour', or '1day'
        start_date: Optional start date filter
        end_date: Optional end date filter
    """
    conn = get_db_connection()

    # Map timeframe to aggregation interval
    timeframe_map = {"5min": "5m", "1hour": "1h", "1day": "1d"}

    interval = timeframe_map.get(timeframe, "5m")

    # Build query based on timeframe
    query = f"""
    SELECT 
        ts_event as timestamp,
        instrument_id,
        MAX(CASE WHEN side = 'B' THEN price END) as bid,
        MAX(CASE WHEN side = 'A' THEN price END) as ask,
        (MAX(CASE WHEN side = 'B' THEN price END) + MAX(CASE WHEN side = 'A' THEN price END)) / 2 as mid_price,
        MAX(CASE WHEN side = 'B' THEN size END) as bid_size,
        MAX(CASE WHEN side = 'A' THEN size END) as ask_size
    FROM trades_data
    WHERE instrument_id = {instrument_id}
    GROUP BY ts_event, instrument_id
    """

    if start_date:
        query += f" AND ts_event >= '{start_date}'"
    if end_date:
        query += f" AND ts_event <= '{end_date}'"

    query += " ORDER BY ts_event DESC LIMIT 10000"

    df = pd.read_sql(query, conn)

    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Resample based on timeframe if needed
        if timeframe != "5min":
            df = df.set_index("timestamp")
            df = (
                df.resample(interval)
                .agg(
                    {
                        "bid": "last",
                        "ask": "last",
                        "mid_price": "last",
                        "bid_size": "sum",
                        "ask_size": "sum",
                    }
                )
                .dropna()
                .reset_index()
            )

    return df


# Get available instruments
# def get_instruments():
#     """Fetch list of available instruments"""
#     conn = get_db_connection()
#     query = "SELECT DISTINCT instrument_id FROM trades_data ORDER BY instrument_id"
#     df = pd.read_sql(query, conn)
#     return df["instrument_id"].tolist()


# Main app
st.title("📊 Market Data Viewer")

# Sidebar controls
with st.sidebar:
    st.header("Controls")

    # Instrument selector
    SYMBOLS = {"SPY": 15144, "QQQ": 13340, "TSLA": 16244}

    # Instrument selector
    symbol = st.selectbox(
        "Select Instrument", options=list(SYMBOLS.keys()), key="instrument_selector"
    )

    instrument_id = SYMBOLS[symbol]

    # Timeframe selector
    timeframe = st.selectbox(
        "Select Timeframe", options=["5min", "1hour", "1day"], key="timeframe_selector"
    )

    # Date range selector
    st.subheader("Date Range")
    use_date_filter = st.checkbox("Use date filter", value=False)

    if use_date_filter:
        start_date = st.date_input(
            "Start Date", value=datetime.now() - timedelta(days=7)
        )
        end_date = st.date_input("End Date", value=datetime.now())
    else:
        start_date = None
        end_date = None

    # Manual refresh button
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# Check if instrument_id or timeframe changed, and reload if so
if (
    st.session_state.prev_instrument_id != instrument_id
    or st.session_state.prev_timeframe != timeframe
):
    # Update session state
    st.session_state.prev_instrument_id = instrument_id
    st.session_state.prev_timeframe = timeframe

    # Clear cache to force reload
    st.cache_data.clear()

# Main content area
try:
    # Fetch data
    with st.spinner(f"Loading {timeframe} data for {instrument_id}..."):
        df = fetch_market_data(instrument_id, timeframe, start_date, end_date)

    if df.empty:
        st.warning(f"No data found for {instrument_id}")
    else:
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            mid_price = df["mid_price"].iloc[0]
            if mid_price is not None:
                st.metric("Current Mid Price", f"${mid_price:.2f}")
            else:
                st.metric("Current Mid Price", "N/A")
        with col2:
            bid = df["bid"].iloc[0]
            ask = df["ask"].iloc[0]
            if bid is not None and ask is not None:
                st.metric("Bid-Ask Spread", f"${(ask - bid):.4f}")
            else:
                st.metric("Bid-Ask Spread", "N/A")
        with col3:
            st.metric("Total Records", len(df))
        with col4:
            st.metric("Timeframe", timeframe)

        # Create candlestick chart
        st.subheader(f"{instrument_id} - {timeframe} Chart")

        fig = go.Figure()

        # Add bid/ask lines
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["bid"],
                name="Bid",
                line=dict(color="green", width=1),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["ask"],
                name="Ask",
                line=dict(color="red", width=1),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["mid_price"],
                name="Mid Price",
                line=dict(color="blue", width=2),
            )
        )

        fig.update_layout(
            title=f"{instrument_id} Price Movement",
            xaxis_title="Time",
            yaxis_title="Price ($)",
            height=500,
            hovermode="x unified",
            template="plotly_white",
        )

        st.plotly_chart(fig, use_container_width=True)

        # Volume chart
        st.subheader("Volume")

        fig_vol = go.Figure()

        fig_vol.add_trace(
            go.Bar(
                x=df["timestamp"],
                y=df["bid_size"],
                name="Bid Size",
                marker_color="green",
                opacity=0.6,
            )
        )

        fig_vol.add_trace(
            go.Bar(
                x=df["timestamp"],
                y=df["ask_size"],
                name="Ask Size",
                marker_color="red",
                opacity=0.6,
            )
        )

        fig_vol.update_layout(
            title="Bid/Ask Volume",
            xaxis_title="Time",
            yaxis_title="Size",
            height=300,
            barmode="group",
            template="plotly_white",
        )

        st.plotly_chart(fig_vol, use_container_width=True)

        # Data table
        with st.expander("📋 View Raw Data"):
            st.dataframe(df.head(100), use_container_width=True, height=400)

            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download Data as CSV",
                data=csv,
                file_name=f"{instrument_id}_{timeframe}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

except Exception as e:
    st.error(f"Error loading data: {e}")
    st.info(
        "Please ensure QuestDB is running and contains data for the selected instrument."
    )

# Footer
st.markdown("---")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
