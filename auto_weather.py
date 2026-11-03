import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
import os
import datetime
import time
import logging
from sqlalchemy import create_engine, inspect, Table, Column, String, Float, MetaData, DateTime, select, func, text
from sqlalchemy.dialects.postgresql import insert
import argparse
from dotenv import load_dotenv
import calendar  # For potential use, but not strictly needed

# -----------------------------
# Load Environment Variables
# -----------------------------
load_dotenv()

# -----------------------------
# Parse Command-Line Arguments
# -----------------------------
parser = argparse.ArgumentParser(description="Fetch and insert weather data for farmer_grid_weather_data")
parser.add_argument(
    "--date",
    type=str,
    help="Specific date for weather data (YYYY-MM-DD). If provided, fetches only for this date.",
    default=None
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
# File Paths
# -----------------------------
base_path = os.path.join(os.path.dirname(__file__), '..')
log_dir = os.path.join(base_path, 'logs')
os.makedirs(log_dir, exist_ok=True)

# Define yesterday for default end_date and log_file
yesterday = datetime.date.today() - datetime.timedelta(days=1)
log_file = os.path.join(log_dir, f"{yesterday.isoformat()}log.txt")

# -----------------------------
# Setup Logging (File and Console)
# -----------------------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')

# File handler
fh = logging.FileHandler(log_file)
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# -----------------------------
# Grid Cells (Moved up for missing detection)
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
grid_ids = [g[2] for g in grid_cells]
logger.info(f"Total grid cells: {len(grid_cells)}")

# -----------------------------
# Determine Date Range and Missing Dates
# -----------------------------
engine = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')

# Define metadata and table
metadata = MetaData()
weather_table = Table(
    'farmer_grid_weather_data',
    metadata,
    Column('dategrid_id', String, primary_key=True),
    Column('date', DateTime),
    Column('grid_id', String),
    Column('grid_lat', Float),
    Column('grid_lon', Float),
    Column('temperature_2m_mean', Float),
    Column('temperature_2m_max', Float),
    Column('temperature_2m_min', Float),
    Column('precipitation_sum', Float),
    Column('et0_fao_evapotranspiration_sum', Float),
    Column('relative_humidity_2m_mean', Float),
    Column('cloud_cover_mean', Float),
    Column('soil_moisture_0_to_7cm_mean', Float),
    Column('soil_temperature_0_to_7cm_mean', Float),
    Column('sunshine_duration', Float),
    Column('wind_speed_10m_max', Float)
)

# Inspector
inspector = inspect(engine)

missing_dates = []  # Will hold list of missing dates to fetch

if args.date:
    try:
        target_date = datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format")
    missing_dates = [target_date]  # Treat as single missing date
    start_date = end_date = target_date
    logger.info(f"Fetching data for specific date: {start_date.isoformat()}")
else:
    end_date = yesterday
    if not inspector.has_table('farmer_grid_weather_data'):
        metadata.create_all(engine, tables=[weather_table])
        logger.info("Created table farmer_grid_weather_data")
        min_date = None
    else:
        with engine.connect() as conn:
            # Get min and max date
            min_stmt = select(func.min(weather_table.c.date))
            max_stmt = select(func.max(weather_table.c.date))
            min_date = conn.execute(min_stmt).scalar()
            max_date = conn.execute(max_stmt).scalar()
            min_date = min_date.date() if min_date else None
            max_date = max_date.date() if max_date else None
    
    if min_date is None:
        print("There is no data in the table please enter start date [yyyy-mm-dd]")
        while True:
            input_str = input().strip()
            try:
                start_date = datetime.datetime.strptime(input_str, "%Y-%m-%d").date()
                break
            except ValueError:
                print("Invalid format. Please enter YYYY-MM-DD")
        expected_dates = pd.date_range(start=start_date, end=end_date).date.tolist()
        # Since empty, all dates missing
        missing_dates = expected_dates
    else:
        start_date = min_date
        if start_date > end_date:
            logger.info("Data start date is after yesterday. No fetch needed.")
            exit(0)
        expected_dates = pd.date_range(start=start_date, end=end_date).date.tolist()
        
        # Query existing date-grid combinations up to end_date
        query = text("""
            SELECT date, grid_id 
            FROM farmer_grid_weather_data 
            WHERE date >= :start_date AND date <= :end_date
        """)
        with engine.connect() as conn:
            existing_df = pd.read_sql(query, conn, params={
                'start_date': start_date,
                'end_date': end_date + pd.Timedelta(days=1)
            })
            if not existing_df.empty:
                existing_df['date_only'] = pd.to_datetime(existing_df['date']).dt.date
                existing_combos = set(zip(existing_df['date_only'], existing_df['grid_id']))
            else:
                existing_combos = set()
        
        # Find missing date-grid combos
        missing_combos = []
        for exp_date in expected_dates:
            for grid_id in grid_ids:  # Use pre-defined grid_ids
                if (exp_date, grid_id) not in existing_combos:
                    missing_combos.append((exp_date, grid_id))
        
        if not missing_combos:
            logger.info(f"Data is fully consistent from {start_date.isoformat()} to {end_date.isoformat()}. No fetch needed.")
            exit(0)
        
        # Get unique missing dates
        missing_dates = sorted(list(set([combo[0] for combo in missing_combos])))
        logger.info(f"Found gaps: Will fetch {len(missing_dates)} missing date(s) from {start_date.isoformat()} to {end_date.isoformat()}. Total missing records: {len(missing_combos)}")

# Ensure table exists
if not inspector.has_table('farmer_grid_weather_data'):
    metadata.create_all(engine, tables=[weather_table])
    logger.info("Created table farmer_grid_weather_data")

# -----------------------------
# Setup API Client
# -----------------------------
cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

# -----------------------------
# Weather Parameters
# -----------------------------
url = "https://archive-api.open-meteo.com/v1/archive"
base_params = {
    "daily": [
        "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
        "precipitation_sum", "et0_fao_evapotranspiration_sum",
        "relative_humidity_2m_mean", "cloud_cover_mean",
        "soil_moisture_0_to_7cm_mean", "soil_temperature_0_to_7cm_mean",
        "sunshine_duration", "wind_speed_10m_max"
    ]
}

# -----------------------------
# Fetch Weather Data for Missing Dates
# -----------------------------
all_weather_data = []

for fetch_date in missing_dates:
    logger.info(f"\nFetching missing date: {fetch_date.isoformat()}")
    
    date_weather_data = []  # Per date
    
    for grid_lat, grid_lon, grid_id in grid_cells:
        logger.info(f"  Processing Grid: {grid_id} ({grid_lat}, {grid_lon}) for {fetch_date.isoformat()}")

        params = base_params.copy()
        params.update({
            "latitude": grid_lat,
            "longitude": grid_lon,
            "start_date": fetch_date.isoformat(),
            "end_date": fetch_date.isoformat()
        })

        # Retry
        for attempt in range(3):
            try:
                responses = openmeteo.weather_api(url, params=params, timeout=120)
                response = responses[0]
                break
            except Exception as e:
                logger.error(f"    Failed on attempt {attempt+1}: {e}")
                time.sleep(5)
        else:
            logger.warning(f"    Skipping after 3 failed attempts")
            continue

        # Process daily data (single day)
        daily = response.Daily()
        daily_data = {
            "date": pd.to_datetime(daily.Time(), unit="s", utc=True),
            "grid_id": grid_id,
            "grid_lat": grid_lat,
            "grid_lon": grid_lon,
            "temperature_2m_mean": daily.Variables(0).ValuesAsNumpy(),
            "temperature_2m_max": daily.Variables(1).ValuesAsNumpy(),
            "temperature_2m_min": daily.Variables(2).ValuesAsNumpy(),
            "precipitation_sum": daily.Variables(3).ValuesAsNumpy(),
            "et0_fao_evapotranspiration_sum": daily.Variables(4).ValuesAsNumpy(),
            "relative_humidity_2m_mean": daily.Variables(5).ValuesAsNumpy(),
            "cloud_cover_mean": daily.Variables(6).ValuesAsNumpy(),
            "soil_moisture_0_to_7cm_mean": daily.Variables(7).ValuesAsNumpy(),
            "soil_temperature_0_to_7cm_mean": daily.Variables(8).ValuesAsNumpy(),
            "sunshine_duration": daily.Variables(9).ValuesAsNumpy(),
            "wind_speed_10m_max": daily.Variables(10).ValuesAsNumpy()
        }
        daily_dataframe = pd.DataFrame(data=daily_data)
        date_weather_data.append(daily_dataframe)
    
    # Append this date's data to all
    if date_weather_data:
        day_weather_df = pd.concat(date_weather_data, ignore_index=True)
        all_weather_data.append(day_weather_df)
    else:
        logger.warning(f"No data fetched for {fetch_date.isoformat()}")

# -----------------------------
# Save to DB
# -----------------------------
# Save weather data with UPSERT
if all_weather_data:
    final_weather_df = pd.concat(all_weather_data, ignore_index=True)
    final_weather_df['dategrid_id'] = final_weather_df.apply(
        lambda row: f"{row['date'].date().isoformat()}_{row['grid_id']}", axis=1
    )
    cols = ['dategrid_id'] + [col for col in final_weather_df.columns if col != 'dategrid_id']
    final_weather_df = final_weather_df[cols]
    logger.info(f"Weather DataFrame columns: {list(final_weather_df.columns)}")
    
    stmt = insert(weather_table).values(final_weather_df.to_dict('records'))
    upsert_stmt = stmt.on_conflict_do_nothing(index_elements=['dategrid_id'])
    
    with engine.connect() as conn:
        result = conn.execute(upsert_stmt)
        conn.commit()
        inserted_count = result.rowcount
    logger.info(f"\nWeather data upserted: {inserted_count} new records for missing dates (skipped duplicates if any)")
else:
    logger.warning(f"\nNo weather data fetched for missing dates!")

engine.dispose()