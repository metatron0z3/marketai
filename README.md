# MarketAI

A Python pipeline for ingesting TBBO data from Databento into QuestDB, running in a Docker container.

## Quick Start

### Prerequisites
- Docker Desktop running (check: `docker info`).
- Python 3.12 (optional for local execution).
- TBBO data file: `data/tbbo/XNAS-20250630-3K464RPTEN.zip`.
- At least 500MB free memory (check: `top -l 1 | grep PhysMem` on macOS).

### 1. Launch Docker Container

2. **Build and run**:
   ```bash
   docker-compose up --build
   ```
   This starts QuestDB and runs `local_ingestion.py` to process TBBO data. QuestDB web console is at `http://localhost:9000`.

3. **Check logs**:
   ```bash
   docker-compose logs
   ```

4. **Stop containers**:
   ```bash
   docker-compose down
   ```

### 2. (Optional) Activate Virtual Environment
For local execution without Docker:
1. **Create and activate virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bincd mar/activate  # On macOS/Linux
   # venv\Scripts\activate  # On Windows
   ```
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   Ensure `libpq` is installed:
   ```bash
   brew install libpq  # On macOS
   ```

3. **Run ingestion locally**:
   ```bash
   python src/local_ingestion.py
   ```

### 3. Connect to QuestDB
- **Web Console**: `http://localhost:9000` (username: `admin`, password: `quest`).
- **PostgreSQL Client**:
  ```bash
  psql -h localhost -p 8812 -U admin -d questdb
  ```
  Password: `quest`
- **Sample Query**:
  ```sql
  SELECT ts_event, symbol, bid_px_00, ask_px_00
  FROM tbbo_data
  WHERE symbol = 'SPY'
  LIMIT 10;
  ```

### Troubleshooting (Updated)

- **Testing Single .dbn.zst File**:
  - Ensure the `XNAS-20250630-3K464RPTEN` folder exists in `data/tbbo/`.
  - Run `docker-compose up --build` to test ingestion of the first `.dbn.zst` file.
  - Check logs: `docker-compose logs` for messages like `Processing single .dbn.zst file`.

- **Container Not Processing Data**:
  - Verify `data/tbbo/XNAS-20250630-3K464RPTEN` contains `.dbn.zst` files.
  - If ingestion fails, reduce `chunk_size` in `src/local_ingestion.py` to 25.

- **QuestDB Connection Issues**:
  - Confirm QuestDB container is running: `docker ps`.
  - Test: `psql -h localhost -p 8812 -U admin -d questdb` (password: `quest`).

- **Virtual Environment Issues**:
  - Activate: `source venv/bin/activate`.
  - Install `libpq`: `brew install libpq`.
  - Run locally: `python src/local_ingestion.py`.

- **Memory Issues**:
  - Check: `top -l 1 | grep PhysMem`.
  - Close apps: `osascript -e 'quit app "Google Chrome"'`.