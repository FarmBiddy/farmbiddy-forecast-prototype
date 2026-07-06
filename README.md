# farmbiddy-forecast-prototype

Multi-sector farm financial forecast (Dairy, Beef, Lamb) using `datasets/multi_sector_farm.json`.

## Run locally (Windows)

```powershell
python -m pip install -r requirements.txt
.\start.bat
```

Or: `py -3 -m uvicorn api.main:app --reload` then open http://127.0.0.1:8000

## CLI forecast

```powershell
py -3 run_forecast.py
py -3 run_forecast.py --sectors dairy,beef
py -3 run_forecast.py --sectors beef
```