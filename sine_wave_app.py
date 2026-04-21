from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
from scipy import signal
from pathlib import Path
import os

app = FastAPI()

# Get the directory where this script is located
BASE_DIR = Path(__file__).parent

# Serve static files (CSS, JS, etc.)
if not os.path.exists(BASE_DIR / "templates"):
    os.makedirs(BASE_DIR / "templates")


def apply_lowpass_filter(data, cutoff_frequency, sampling_rate=1000):
    """
    Apply a Butterworth low-pass filter to the data.
    
    Args:
        data: Input signal array
        cutoff_frequency: Cutoff frequency in Hz
        sampling_rate: Sampling rate in Hz
    
    Returns:
        Filtered signal
    """
    if cutoff_frequency <= 0 or cutoff_frequency >= sampling_rate / 2:
        return data

    # Design Butterworth low-pass filter
    nyquist_frequency = sampling_rate / 2
    normalized_cutoff = cutoff_frequency / nyquist_frequency
    
    # Create filter coefficients
    b, a = signal.butter(4, normalized_cutoff, btype='low')
    
    # Apply filter
    filtered_data = signal.filtfilt(b, a, data)
    return filtered_data


@app.get("/")
async def read_root():
    """Serve the main HTML page"""
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/api/wave")
async def get_wave(
    frequency: float = 1.0,
    amplitude: float = 1.0,
    use_lowpass: bool = False,
    lowpass_cutoff: float = 5.0,
    num_points: int = 1000
):
    """
    Generate sine wave data with optional low-pass filtering.
    
    Args:
        frequency: Frequency of the sine wave
        amplitude: Amplitude of the sine wave
        use_lowpass: Whether to apply low-pass filter
        lowpass_cutoff: Cutoff frequency for low-pass filter
        num_points: Number of points to generate
    
    Returns:
        JSON with x and y coordinates for the wave
    """
    try:
        # Validate inputs
        if frequency <= 0 or frequency > 100:
            raise ValueError("Frequency must be between 0 and 100")
        if amplitude <= 0 or amplitude > 10:
            raise ValueError("Amplitude must be between 0 and 10")
        if num_points < 10 or num_points > 5000:
            raise ValueError("Number of points must be between 10 and 5000")
        
        # Generate x values (time points)
        x = np.linspace(0, 4 * np.pi, num_points)
        
        # Generate sine wave
        y = amplitude * np.sin(frequency * x)
        
        # Apply low-pass filter if enabled
        if use_lowpass and lowpass_cutoff > 0:
            # Sampling rate based on the number of points
            sampling_rate = num_points / (4 * np.pi)
            y = apply_lowpass_filter(y.copy(), lowpass_cutoff, sampling_rate)
        
        # Return data as JSON
        return JSONResponse({
            "x": x.tolist(),
            "y": y.tolist(),
            "frequency": frequency,
            "amplitude": amplitude,
            "use_lowpass": use_lowpass,
            "lowpass_cutoff": lowpass_cutoff
        })
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating wave: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI server on http://localhost:8000")
    print("Open http://localhost:8000 in your browser")
    uvicorn.run(app, host="127.0.0.1", port=8000)
