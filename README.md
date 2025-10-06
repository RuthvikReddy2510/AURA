# Aircraft Proximity Tracker

A real-time dashboard to:

- Track aircraft near selected airports using the OpenSky API
- Detect proximity conflicts with ALARM, ALERT, or WARNING levels
- Visualize aircraft on a live map
- Display conflicting flight pairs in a dynamic table

---

## Requirements

- Python 3.9 or higher

---

## Setup

Install the required Python libraries:

pip install flask requests

---

## How to Run

Run the Flask server:

python server.py

Open your browser and go to:

http://127.0.0.1:5000

---

## Project Structure

- server.py – Flask application entry point
- adsb_analysis.py – Aircraft data fetch + alert detection
- airport_config.py – Airport coordinates
- threshold_config.py – Thresholds for proximity alerts
- templates/ – HTML templates (map, layout, table)
- static/ – Icons and logo assets

---