"""
MarketPilot Research - Dataset Builder.

Saves DataFrames into efficient Parquet format for institutional analytics.
"""

import pandas as pd
from pathlib import Path
from loguru import logger

class DatasetBuilder:
    def __init__(self, output_dir: str = "dataset"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def save_features(self, df: pd.DataFrame, filename: str = "features.parquet") -> str:
        """Saves a feature DataFrame to parquet format."""
        if df.empty:
            logger.warning("Empty dataframe provided. Skipping save.")
            return ""
            
        filepath = self.output_dir / filename
        df.to_parquet(filepath, engine="pyarrow", compression="snappy")
        logger.info(f"Saved {len(df)} feature records to {filepath}")
        return str(filepath)
        
    def save_trades(self, df: pd.DataFrame, filename: str = "trades.parquet") -> str:
        """Saves raw trade execution data to parquet format."""
        if df.empty:
            return ""
            
        filepath = self.output_dir / filename
        df.to_parquet(filepath, engine="pyarrow", compression="snappy")
        logger.info(f"Saved {len(df)} trade records to {filepath}")
        return str(filepath)
