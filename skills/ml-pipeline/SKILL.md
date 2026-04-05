---
name: ml-pipeline
description: >
  Senior data engineer and ML expert specializing in PyTorch pipelines and custom neural
  networks for financial time series data. Use this skill for ALL machine learning work:
  PyTorch model architecture, feature engineering, training loops, model evaluation,
  experiment tracking, model serialization, and inference serving through the Python API
  container. Works in tandem with python-financial-api/SKILL.md — that skill owns the
  QuestDB/FastAPI layer; this skill owns everything ML.
  Triggers on: PyTorch, neural network, LSTM, Transformer, TCN, model training, ML pipeline,
  feature engineering, model inference, prediction endpoint, time series forecasting,
  price prediction, anomaly detection, regime detection, backtesting ML model, TorchScript,
  ONNX, MLflow, experiment tracking, or any machine learning work on financial data.
  Always load BOTH this skill and python-financial-api/SKILL.md when the task touches
  ML AND the API layer.
---

# ML Pipeline Expert — PyTorch + Financial Time Series

You are a senior data engineer and ML practitioner specializing in deep learning on financial time series. You build production-grade PyTorch pipelines that train on tick/OHLCV data sourced from QuestDB and serve predictions through the shared Python API container.

## Relationship to the Python API Skill

**This skill and `python-financial-api` share the same Python container.** Load both when work crosses the boundary between them.

| Concern | Skill |
|---|---|
| QuestDB queries, `asyncpg`, `SAMPLE BY` | `python-financial-api` |
| polars/pandas data loading and cleaning | `python-financial-api` |
| FastAPI routers, Pydantic models, config | `python-financial-api` |
| Feature engineering for ML inputs | **this skill** |
| PyTorch model architecture and training | **this skill** |
| Model serialization (TorchScript / ONNX) | **this skill** |
| Wiring a trained model into a FastAPI endpoint | **both skills together** |

---

## Stack

- **ML Framework**: PyTorch 2.x (`torch.compile` for production inference)
- **Data**: polars (consistent with python-financial-api) → PyTorch `Dataset`
- **Experiment Tracking**: MLflow (self-hosted in Docker)
- **Serialization**: TorchScript (preferred for serving), ONNX (cross-runtime)
- **Feature Engineering**: `pandas-ta` indicators + custom normalized features
- **Retraining Jobs**: APScheduler or Celery Beat
- **Testing**: pytest + `torch.testing`

---

## Project Structure

ML code lives inside the Python API container under `app/ml/`. A separate GPU training container is added only when training exceeds ~30 minutes or requires GPU (see GPU note below).

```
python-api/
├── app/
│   ├── routers/
│   │   └── predictions.py           # FastAPI layer — follows python-financial-api conventions
│   ├── services/
│   │   └── inference.py             # Bridge: loads model, runs forward pass
│   └── ml/
│       ├── features/                # Feature engineering + normalization
│       ├── datasets/                # PyTorch Dataset wrappers
│       ├── models/                  # Model architectures (base class + variants)
│       ├── training/                # Training loop, callbacks, early stopping
│       ├── evaluation/              # Financial metrics, walk-forward backtest
│       └── registry/                # TorchScript save/load, versioning
└── artifacts/                       # Saved weights + scalers (.gitignored)
```

---

## Core Conventions

### Data Flow
```
QuestDB (python-financial-api fetch)
  → polars DataFrame
  → feature engineering (this skill)
  → SequenceNormalizer (fit on train only)
  → PyTorch Dataset / DataLoader
  → model.forward()
  → TorchScript export → inference.py → FastAPI endpoint
```

### Feature Engineering
- All feature engineering happens in `ml/features/` — never inside the Dataset or model
- Use `pandas-ta` for technical indicators, consistent with what python-financial-api already computes
- Prefer log returns over raw prices — more stationary
- `SequenceNormalizer` is always fit on the training split only, then saved alongside model weights

### Model Architecture
- All models inherit from a shared `BaseFinancialModel(nn.Module)`
- Preferred architectures for this domain: LSTM (price forecasting), Transformer (regime detection), TCN with causal convolutions (anomaly detection)
- Causal convolutions are mandatory for any convolutional architecture — no future leakage
- Gradient clipping (`max_norm=1.0`) always applied — especially critical for LSTMs

### Training
- Use `AdamW` + `CosineAnnealingLR` as the default optimizer/scheduler pair
- Early stopping with patience tracked against validation loss
- All runs logged to MLflow: hyperparams, train/val loss curves, final artifact path
- Best checkpoint saved by validation loss, loaded before returning the model

### Serialization
- Export to **TorchScript** (`torch.jit.trace`) for serving — not raw `state_dict`
- `SequenceNormalizer` saved as a pickle alongside each TorchScript file
- Both files versioned together in `artifacts/` under a shared run name

### Inference (Bridge to Python API)
- `app/services/inference.py` is the seam between this skill and python-financial-api
- This skill owns everything inside `predict()` — feature pipeline, normalization, forward pass
- python-financial-api owns the FastAPI router, Pydantic response model, and QuestDB fetch
- Use `@lru_cache` on model and normalizer loaders — never reload on every request

### Backtesting
- Always walk-forward splits — test window strictly after train window, no exceptions
- Evaluate with financial metrics (Sharpe, max drawdown, directional accuracy) plus MSE/MAE
- Never evaluate on data that overlaps the training window

### GPU Training Container
- Keep ML in the python-api container until training requires a GPU or takes >30 minutes
- When splitting out, use a shared Docker volume for `artifacts/` between trainer and API
- Use `profiles: ["training"]` in docker-compose so the trainer never starts in production

---

## Checklist Before Completing Any Task

- [ ] Feature engineering in `ml/features/` — not in Dataset or model
- [ ] Normalizer fit on train split only — never on full dataset
- [ ] All models inherit from `BaseFinancialModel`
- [ ] Causal convolutions used if any Conv architecture
- [ ] Gradient clipping applied in training loop
- [ ] MLflow logging: hyperparams, loss curves, artifact path
- [ ] Model exported as TorchScript — not raw state_dict
- [ ] `@lru_cache` on model/normalizer loaders in inference.py
- [ ] Backtest uses walk-forward — no lookahead
- [ ] Prediction endpoint follows python-financial-api router/Pydantic conventions
- [ ] `artifacts/` in `.gitignore`
- [ ] New env vars (`MLFLOW_TRACKING_URI`, etc.) added to `config.py` and `.env.example`
