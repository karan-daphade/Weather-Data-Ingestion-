import pandas as pd
from sqlalchemy import create_engine, text
import argparse
from dotenv import load_dotenv
import os
import logging
from datetime import datetime, date

# -----------------------------
# Load Environment Variables
# -----------------------------
load_dotenv()

# -----------------------------
# Parse Command-Line Arguments
# -----------------------------
parser = argparse.ArgumentParser(description="Check consistency of weather data in farmer_grid_weather_data table")
parser.add_argument(
    "--start_date",
    type=str,
    required=True,
    help="Start date for checking data consistency (YYYY-MM-DD)"
)
parser.add_argument(
    "--end_date",
    type=str,
    required=True,
    help="End date for checking data consistency (YYYY-MM-DD)"
)
args = parser.parse_args()

# -----------------------------
# DB Credentials
# -----------------------------
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')

# -----------------------------
# Setup Logging (Console only for simplicity)
# -----------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# -----------------------------
# Connect to DB
# -----------------------------
engine = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')

# -----------------------------
# Parse Dates
# -----------------------------
try:
    start_date_obj = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end_date_obj = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    if start_date_obj > end_date_obj:
        raise ValueError("Start date must be before or equal to end date")
except ValueError as e:
    logger.error(f"Invalid date format or logic: {e}")
    exit(1)

expected_dates = pd.date_range(start=start_date_obj, end=end_date_obj).date.tolist()
num_expected_days = len(expected_dates)
logger.info(f"Checking data consistency from {start_date_obj} to {end_date_obj} ({num_expected_days} days)")

# -----------------------------
# Hardcoded Grid Cells (from download script)
# -----------------------------
grid_cells = [
    (19.6, 75.9, "GRID_0001"), (19.6, 76.0, "GRID_0002"), (19.6, 76.1, "GRID_0003"),
    (19.7, 75.9, "GRID_0004"), (19.7, 76.0, "GRID_0005"), (19.7, 76.1, "GRID_0006"),
    (19.8, 75.9, "GRID_0007"), (19.8, 76.0, "GRID_0008"), (19.8, 76.1, "GRID_0009"),
    (20.9, 78.3, "GRID_0010"), (20.9, 78.4, "GRID_0011"), (20.9, 78.5, "GRID_0012"),
    (21.0, 78.3, "GRID_0013"), (21.0, 78.5, "GRID_0014"), (21.1, 78.3, "GRID_0015"),
    (21.1, 78.4, "GRID_0016"), (21.1, 78.5, "GRID_0017"), (21.2, 78.3, "GRID_0018"),
    (21.2, 78.4, "GRID_0019")
]
grid_ids = [grid_id for _, _, grid_id in grid_cells]
num_grids = len(grid_ids)
expected_total_records = num_grids * num_expected_days

logger.info(f"Expected total records: {expected_total_records} (across {num_grids} grids)")

# -----------------------------
# Query Existing Data in Date Range
# -----------------------------
query = text("""
    SELECT date, grid_id 
    FROM farmer_grid_weather_data 
    WHERE date >= :start_date AND date <= :end_date
""")
with engine.connect() as conn:
    df = pd.read_sql(query, conn, params={
        'start_date': start_date_obj,
        'end_date': end_date_obj + pd.Timedelta(days=1)  # Exclusive end for DateTime
    })
    df['date_only'] = pd.to_datetime(df['date']).dt.date

if df.empty:
    logger.warning("No data found in the specified date range!")
    exit(0)

actual_total_records = len(df)
logger.info(f"Found {actual_total_records} records in the date range")

if actual_total_records == expected_total_records:
    logger.info("✅ Data is fully consistent: All expected date-grid combinations present!")
    exit(0)

# -----------------------------
# Check per Grid
# -----------------------------
missing_summary = {}
complete_grids = 0

for grid_id in grid_ids:
    grid_data = df[df['grid_id'] == grid_id]
    existing_dates = set(grid_data['date_only'].unique())
    grid_missing_dates = set(expected_dates) - existing_dates
    num_missing = len(grid_missing_dates)
    
    if num_missing == 0:
        complete_grids += 1
        logger.info(f"✅ Grid {grid_id}: Complete ({len(existing_dates)}/{num_expected_days} days)")
    else:
        missing_summary[grid_id] = sorted(grid_missing_dates)
        logger.warning(f"⚠️  Grid {grid_id}: Missing {num_missing}/{num_expected_days} days")
        for missing_date in sorted(grid_missing_dates):
            logger.warning(f"   - Missing: {missing_date}")

logger.info(f"\nSummary: {complete_grids}/{num_grids} grids complete. Total missing records: {expected_total_records - actual_total_records}")

if missing_summary:
    logger.info("\nDetailed missing dates per grid:")
    for grid_id, misses in missing_summary.items():
        logger.info(f"Grid {grid_id}: {', '.join([d.isoformat() for d in misses])}")
else:
    logger.info("No missing data found per grid.")

# Close connection
engine.dispose()