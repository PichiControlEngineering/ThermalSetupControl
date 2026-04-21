# Oscillating Sine Wave with Low-Pass Filter

A FastAPI web application that displays an oscillating sine wave with interactive controls for frequency and amplitude, plus an optional low-pass filter.

## Features

- **Real-time sine wave visualization** rendered on an HTML5 canvas
- **Frequency slider** (0.1–5.0 Hz) - control how many cycles appear
- **Amplitude slider** (0.1–2.0) - control wave height
- **Low-Pass Filter toggle** - enable/disable filtering
- **Cutoff Frequency slider** (0.5–50 Hz) - adjust filter characteristics when enabled
- **Python backend** using FastAPI with scipy signal processing
- **Responsive design** that works on desktop and mobile

## Installation

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Navigate to the project directory** (if not already there):
   ```bash
   cd c:\Users\gertv\Documents\Werk\RemoteLabsProject\PythonProject
   ```

## Running the Application

Start the FastAPI server:

```bash
python sine_wave_app.py
```

You should see output like:
```
Starting FastAPI server on http://localhost:8000
Open http://localhost:8000 in your browser
```

Then open your browser and go to: **http://localhost:8000**

## How It Works

### Backend (Python/FastAPI)
- `/api/wave` endpoint generates sine wave data with optional low-pass filtering
- Uses SciPy's Butterworth filter for smooth signal attenuation
- Returns JSON data with x and y coordinates for the wave

### Frontend (HTML/JavaScript)
- Fetches wave data from the backend API
- Renders the wave on an HTML5 canvas
- Real-time updates as you move sliders
- Shows/hides the cutoff frequency slider based on filter state

## API Endpoint

**GET** `/api/wave`

Query parameters:
- `frequency` (float, default: 1.0) - Wave frequency in Hz
- `amplitude` (float, default: 1.0) - Wave amplitude
- `use_lowpass` (bool, default: false) - Enable low-pass filter
- `lowpass_cutoff` (float, default: 5.0) - Filter cutoff frequency in Hz
- `num_points` (int, default: 1000) - Number of points to generate

Example:
```
http://localhost:8000/api/wave?frequency=2&amplitude=1.5&use_lowpass=true&lowpass_cutoff=10
```

## Project Structure

```
├── sine_wave_app.py          # FastAPI application
├── templates/
│   └── index.html             # Frontend HTML/CSS/JavaScript
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Requirements

- Python 3.8+
- FastAPI
- Uvicorn (ASGI server)
- NumPy
- SciPy

## Notes

- The low-pass filter uses a 4th-order Butterworth filter for smooth attenuation
- The filter becomes active only when both the filter is enabled AND a cutoff frequency is set
- The web interface handles responsive canvas resizing for any screen size
- All computations are done on the backend (Python) and cached on the frontend
