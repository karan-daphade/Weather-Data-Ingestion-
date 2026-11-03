# Agricultural Weather Data Ingestion & Consistency Pipeline

An automated Python data pipeline that fetches, verifies, and stores historical agrometeorological weather data from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) into a PostgreSQL database.

The project is tailored for agricultural monitoring across 19 predefined geographical grid cells (covering regions in Maharashtra, India: latitudes 19.6°N–21.2°N, longitudes 75.9°E–78.5°E).

---

## 📌 Features

- **Automated Missing Data & Gap Detection**: Automatically detects date/grid gaps in the database and downloads only missing records.
- **Incremental Daily Updates**: Determines the latest date in the database and ingests new data up to yesterday.
- **Targeted Single-Day Ingestion**: Supports fetching weather data for any arbitrary specific date using `--date YYYY-MM-DD`.
- **Robust API Client**: Configured with request caching (`requests-cache`) and exponential retry backoff (`retry-requests`) to handle API timeouts and rate-limiting gracefully.
- **PostgreSQL Upsert**: Uses SQLAlchemy with PostgreSQL `ON CONFLICT (dategrid_id) DO NOTHING` to prevent duplicate entries while maintaining data integrity.
- **Data Consistency Audit**: Dedicated verification script (`check.py`) to audit missing days/records across all monitored grid points.
- **Dual Logging**: Real-time console logs and dated log files.

---

## 📁 Repository Structure

```text
├── auto_weather.py        # Smart pipeline with gap detection & backfilling
├── auto_weatherdata.py    # Incremental date-range pipeline (from max date to yesterday)
├── check.py               # Data consistency & completeness audit tool
├── requirements.txt       # Python package dependencies
├── .env.example           # Example environment variable template
├── .gitignore             # Git ignore configuration
└── README.md              # Project documentation
```

---

## 🗺️ Monitored Grid Cells

The pipeline tracks 19 distinct spatial grid locations:

| Grid ID | Latitude | Longitude | Grid ID | Latitude | Longitude |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GRID_0001` | 19.6°N | 75.9°E | `GRID_0011` | 20.9°N | 78.4°E |
| `GRID_0002` | 19.6°N | 76.0°E | `GRID_0012` | 20.9°N | 78.5°E |
| `GRID_0003` | 19.6°N | 76.1°E | `GRID_0013` | 21.0°N | 78.3°E |
| `GRID_0004` | 19.7°N | 75.9°E | `GRID_0014` | 21.0°N | 78.5°E |
| `GRID_0005` | 19.7°N | 76.0°E | `GRID_0015` | 21.1°N | 78.3°E |
| `GRID_0006` | 19.7°N | 76.1°E | `GRID_0016` | 21.1°N | 78.4°E |
| `GRID_0007` | 19.8°N | 75.9°E | `GRID_0017` | 21.1°N | 78.5°E |
| `GRID_0008` | 19.8°N | 76.0°E | `GRID_0018` | 21.2°N | 78.3°E |
| `GRID_0009` | 19.8°N | 76.1°E | `GRID_0019` | 21.2°N | 78.4°E |
| `GRID_0010` | 20.9°N | 78.3°E | | | |

---

## 📊 Weather Parameters Collected

Daily agrometeorological metrics fetched from Open-Meteo:

| Parameter Field | Description |
| :--- | :--- |
| `dategrid_id` | Primary Key: combination of date and grid ID (e.g. `2024-01-15_GRID_0001`) |
| `date` | Timestamp (UTC) |
| `grid_id` | Identifier of the grid point |
| `grid_lat`, `grid_lon` | Latitude and longitude coordinates |
| `temperature_2m_mean` | Daily mean 2-meter air temperature (°C) |
| `temperature_2m_max` | Daily maximum 2-meter air temperature (°C) |
| `temperature_2m_min` | Daily minimum 2-meter air temperature (°C) |
| `precipitation_sum` | Total daily precipitation (rain, showers, snow) (mm) |
| `et0_fao_evapotranspiration_sum` | Daily reference evapotranspiration (FAO-56 Penman-Monteith) (mm) |
| `relative_humidity_2m_mean` | Daily mean 2-meter relative humidity (%) |
| `cloud_cover_mean` | Daily mean total cloud cover (%) |
| `soil_moisture_0_to_7cm_mean` | Daily mean volumetric soil moisture in 0–7 cm depth (m³/m³) |
| `soil_temperature_0_to_7cm_mean`| Daily mean soil temperature in 0–7 cm depth (°C) |
| `sunshine_duration` | Daily sunshine duration (seconds) |
| `wind_speed_10m_max` | Maximum wind speed at 10 meters (km/h) |

---

## ⚙️ Database Schema

The table `farmer_grid_weather_data` is automatically initialized on first run if it does not exist:

```sql
CREATE TABLE farmer_grid_weather_data (
    dategrid_id VARCHAR PRIMARY KEY,
    date TIMESTAMP WITHOUT TIME ZONE,
    grid_id VARCHAR,
    grid_lat FLOAT,
    grid_lon FLOAT,
    temperature_2m_mean FLOAT,
    temperature_2m_max FLOAT,
    temperature_2m_min FLOAT,
    precipitation_sum FLOAT,
    et0_fao_evapotranspiration_sum FLOAT,
    relative_humidity_2m_mean FLOAT,
    cloud_cover_mean FLOAT,
    soil_moisture_0_to_7cm_mean FLOAT,
    soil_temperature_0_to_7cm_mean FLOAT,
    sunshine_duration FLOAT,
    wind_speed_10m_max FLOAT
);
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.9+
- PostgreSQL database instance
- Git (for version control)

### 2. Clone or Navigate to the Project Directory
```bash
git clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>
```

### 3. Create and Activate a Virtual Environment
- **On Linux/macOS:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```
- **On Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
- **On Windows (Command Prompt):**
  ```cmd
  python -m venv venv
  venv\Scripts\activate.bat
  ```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Create a `.env` file in the root directory (you can copy `.env.example`):
```bash
cp .env.example .env
```
Edit `.env` and fill in your PostgreSQL credentials:
```env
DB_USER=your_db_username
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database_name
```

---

## 💻 Usage

### 1. Run Automated Ingestion with Gap Detection (`auto_weather.py`)
This is the recommended script for daily scheduled tasks (cron/Task Scheduler) or initial backfilling.

- **Automatic Gap Detection & Ingestion:**
  ```bash
  python auto_weather.py
  ```
  - If the database is empty, it prompts you to provide a start date (`YYYY-MM-DD`).
  - If data already exists, it checks for missing dates or missing grid cells and fetches only the missing records up to yesterday.
  - If data is already up-to-date and complete, it exits cleanly.

- **Fetch a Specific Date:**
  ```bash
  python auto_weather.py --date 2024-06-15
  ```

---

### 2. Run Incremental Range Ingestion (`auto_weatherdata.py`)
Fetches all dates sequentially from `MAX(date) + 1` up to yesterday:
```bash
python auto_weatherdata.py
```
Or for a specific date:
```bash
python auto_weatherdata.py --date 2024-06-15
```

---

### 3. Verify Data Consistency (`check.py`)
Audits database completeness for all 19 grid points across any date window:
```bash
python check.py --start_date 2024-01-01 --end_date 2024-12-31
```
Output includes:
- Total expected records vs actual records in the database.
- A status check for each of the 19 grids (`✅ Complete` or `⚠️ Missing`).
- Detailed list of specific missing dates per grid cell.

---

## 📝 Logging & Caching

- **API Cache**: Uses SQLite caching via `requests-cache` (saved as `.cache.sqlite` in the working directory) to prevent duplicate API hits for identical parameters.
- **Logs**: Execution logs are output to the terminal and saved to `../logs/<YYYY-MM-DD>log.txt`.

---

## 📤 Pushing This Project to GitHub

Follow these steps to initialize Git and push this project to your new GitHub repository:

1. **Initialize Git repository**:
   ```bash
   git init
   ```

2. **Stage and commit files**:
   ```bash
   git add .
   git commit -m "Initial commit: agricultural weather data ingestion and consistency pipeline"
   ```

3. **Set main branch**:
   ```bash
   git branch -M main
   ```

4. **Link your GitHub repository**:
   Create a new repository on [GitHub](https://github.com/new) (do not initialize with README or .gitignore since we already have them).
   ```bash
   git remote add origin https://github.com/<your-username>/<your-repo-name>.git
   ```

5. **Push code to GitHub**:
   ```bash
   git push -u origin main
   ```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) (or choose your preferred license).

