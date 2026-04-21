# -*- coding: utf-8 -*-
import time
import clr
import threading
import numpy as np
import matplotlib.pyplot as plt
import ipywidgets as widgets
import os
import csv
import control as ct
from datetime import datetime

# Load ASAM assemblies from the global assembly cache (GAC)
clr.AddReference("ASAM.XIL.Implementation.TestbenchFactory, Version=2.1.0.0, Culture=neutral, PublicKeyToken=fc9d65855b27d387")
clr.AddReference("ASAM.XIL.Interfaces, Version=2.1.0.0, Culture=neutral, PublicKeyToken=bf471dff114ae984")

# Import XIL API .NET classes from the .NET assemblies
from ASAM.XIL.Implementation.TestbenchFactory.Testbench import TestbenchFactory # pyright: ignore[reportMissingImports]
from ASAM.XIL.Interfaces.Testbench.Common.Error import TestbenchPortException # pyright: ignore[reportMissingImports]
from ASAM.XIL.Interfaces.Testbench.Common.Capturing.Enum import CaptureState # pyright: ignore[reportMissingImports]
from ASAM.XIL.Interfaces.Testbench.MAPort.Enum import MAPortState # pyright: ignore[reportMissingImports]

# This class is responsible for interfacing with the dSPACE DS1104 hardware, 
# allowing for reading sensor data and writing control inputs to the plant.
class ThermalControlApparatus():
    # setup
    def __init__(self):
        IsMPSystem = False
        MAPortConfigFile = r".\PortConfigurations\MAPortConfigDS1104.xml"
        Task = "HostService"
        MyTestbenchFactory = TestbenchFactory()
        self.MyTestbench = MyTestbenchFactory.CreateVendorSpecificTestbench("dSPACE GmbH", 
                                                                            "XIL API", "2020-B")

        self.MyMAPortFactory = self.MyTestbench.MAPortFactory
        self.MyValueFactory = self.MyTestbench.ValueFactory
        self.MyCapturingFactory = self.MyTestbench.CapturingFactory

        self.MAPort = self.MyMAPortFactory.CreateMAPort("setupMAPort")
        self.MAPortConfig = self.MAPort.LoadConfiguration(MAPortConfigFile)
        
        self.MAPort.Configure(self.MAPortConfig, False)

        # Signal paths
        self.signal_t1 = "Model Root/Gain_t1/Out1"
        self.signal_t2 = "Model Root/Gain_t2/Out1" 
        self.signal_fan = "Model Root/input_fan/Value"
        self.signal_heater = "Model Root/input_heat/Value"
        self.signal_vane = "Model Root/input_vane/Value"

        # Shutdown time for safety procedures
        self.triggered_shutdown_time = None

        # Safety check thread control
        self._safety_thread = None
        self._safety_thread_stop = threading.Event()

        # Stop event for the live control loop
        self.stop_event = threading.Event()


    def _periodic_safety_check(self):
        while not self._safety_thread_stop.is_set():
            try:
                t1 = self.read_t1()
                t2 = self.read_t2()
                self.safetycheck(t1, t2)
            except Exception as e:
                print(f"Error in periodic safety check: {e}")
            self._safety_thread_stop.wait(5)  # Wait 5 seconds or until stop
    
    # Startup methods
    def start(self):
        print('Connecting to the Thermal Control Apparatus...')
        if self._safety_thread is None or not self._safety_thread.is_alive():
            self._safety_thread_stop.clear()
            self._safety_thread = threading.Thread(target=self._periodic_safety_check, daemon=True)
            self._safety_thread.start()

    def stop(self):
        # Call this to stop the background safety check thread
        self._safety_thread_stop.set()
        if self._safety_thread is not None:
            self._safety_thread.join(timeout=2)
            self._safety_thread = None

    ##############################################
    # Methods for reading and writing plant data #
    ##############################################
    def read_t1(self):
        return self.MAPort.Read(self.signal_t1).Value

    def read_t2(self):
        return self.MAPort.Read(self.signal_t2).Value

    def write_fan(self, fan_input):
        if self.triggered_shutdown_time is None:
            self.MAPort.Write(self.signal_fan, self.MyValueFactory.CreateFloatValue(fan_input))
        else:
            self.update_safetycheck()

    def write_heater(self, heater_input):
        if self.triggered_shutdown_time is None:
            self.MAPort.Write(self.signal_heater, self.MyValueFactory.CreateFloatValue(heater_input))
        else:
            self.update_safetycheck()
            
    def write_vane(self, vane_input):
        self.MAPort.Write(self.signal_vane, self.MyValueFactory.CreateFloatValue(vane_input))

    # Method to read all supplied inputs at once (heater, fan, vane)
    def read_inputs(self):
        # Output order: heater, fan, vane
        return [self.MAPort.Read(i).Value for i in [self.signal_heater, self.signal_fan, self.signal_vane]]
    
    ############################ Safety Check Methods ############################
    # Methods for Safety check: if t1 exceeds 100 degrees, turn off heater and open vane
    ##############################################################################

    def safetycheck(self, signal_t1, signal_t2, t_shutdown = 30.0):
        safety_temperature = 80.0 # Temperature cannot exceed this amount
        if any([T > safety_temperature for T in [signal_t1, signal_t2]]): #Heater exceeded safe temperature
            self.cooling_down()
            self.triggered_shutdown_time = time.time() + t_shutdown  # Set shutdown time to 30 seconds
            print(f"Safety check triggered: Temperature exceeded {safety_temperature} degrees. Cooling down initiated.")

    def update_safetycheck(self):
        if self.triggered_shutdown_time is not None:
            if time.time() > self.triggered_shutdown_time:
                self.triggered_shutdown_time = None

    
    def cooling_down(self):
        # call then when done experimenting
        self.write_heater(0.0)
        self.write_vane(0.0)
        self.write_fan(10.0)

    #########################################################################
    ##                   Online control loop function                      ##
    #########################################################################
    def control_loop(self, plant, controller, control_duration=60, dt=0.1):
        # This function implements the control loop for a particular duration of time, the inputs are:
        # Plant: The thermal control apparatus object, which interacts with the
        start_time = time.time()
        self.stop_event.clear()

        # Setting button function
        stop_control_button = widgets.Button(description="Stop Controller",     
                                    button_style='danger')
        display(stop_control_button) # pyright: ignore[reportUndefinedVariable]
        stop_control_button.on_click(self.stop_controller)

        # Initialize integral error
        integral_error = 0.0

        # Online control loop
        while time.time() - start_time < control_duration:
            if self.stop_event.is_set():
                print("Experiment duration exceeded, Controller stopped.")
                break
            # Read current temperature
            T_current = plant.read_t1()  # Assuming T1 is the temperature to control

            #Retrieve control inputs from the controller function
            heater_power, fan_power, vane_rotation, integral_error = controller(T_current, int_error=integral_error)
            # Write control input to the plant
            plant.write_heater(heater_power)
            plant.write_fan(fan_power)
            plant.write_vane(vane_rotation)

            # Wait for the next control loop iteration
            time.sleep(dt)
            # If control loop is finished, turn off heater and put on fan
        plant.write_heater(0)
        plant.write_fan(10)
        plant.write_vane(0)

    def stop_controller(self, b):
        current_time = datetime.now().strftime("%H:%M")
        display(f"Controller stopped manually at {current_time}") # pyright: ignore[reportUndefinedVariable]
        self.stop_event.set()
        self.stop_control_button.on_click(self.stop_controller)

# This class is responsible for collecting measurement data from the plant and saving it to a CSV file. 
# It runs in a separate thread to ensure that data collection does not block the main thread, allowing 
# for real-time control and monitoring of the plant.
class CollectMeasurementData:
    def __init__(self, plant, fs = 10.0, Exp_length_minutes = 25, save_dir = r"C:\Thermal\Project_Thermal\ExperimentData", display_button=True):
        
        # Remote-labs file destination for exporting out of clustermarket
        clustermarket_dir = "Z:\Exp_Data_Out"
        if os.path.exists(clustermarket_dir):
            save_dir = clustermarket_dir

        # Define the sampling frequency (Hz) and experiment length (minutes)
        self.dt = 1/fs
        self.Exp_length_sec = Exp_length_minutes * 60

        # Check if plant object is provided
        if plant is None:
            raise ValueError("Plant object must be provided, otherwise the experiment cannot be run.")
        else:
            self.plant = plant

        # Create stop condition
        self._stop_event = threading.Event()
        self._thread = None

        # Optional: Display button to start measurement for the student
        if display_button: 
            # Create Button widget for stopping and starting the experiment
            self.start_button = widgets.Button(description="Start measurment",
                                            button_style='success')
            self.start_button.on_click(self._on_start_clicked)

            self.stop_button = widgets.Button(description="Stop Measurement",     
                                        button_style='danger')
            self.stop_button.on_click(self._on_stop_clicked)
            button_box = widgets.HBox([self.start_button, self.stop_button])
            display(button_box) # pyright: ignore[reportUndefinedVariable]

        # Ensure save directory exists
        file_list = os.listdir(save_dir)
        if len(file_list) > 5:
            i_lastfile = len(file_list) - 5
            # Remove the oldest files if there are more than 5 files
            for f in file_list[0:i_lastfile]:
                file_path = os.path.join(save_dir, f)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        os.makedirs(save_dir, exist_ok=True)

        # Define file location and name with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.filename = os.path.join(save_dir, f"ExperimentData_{timestamp}.csv")

        # Open the CSV file for writing
        self.file = open(self.filename, mode='w', newline='')
        self.writer = csv.writer(self.file)

        # Write the header row
        self.writer.writerow(['Time (s)', 'T1 (°C)', 'T2 (°C)', 'Heater Input (V)', 'Fan Input (V)', 'Vane Input (V)'])
        self.file.flush()  # Ensure header is written to disk
        print(f"Data logging to: {self.filename}")
        
    def _run(self):
        sample_count = 0
        start_perf_time = time.perf_counter()  # Use high-resolution timer
        
        while not self._stop_event.is_set():
            # Calculate exact time this sample should occur
            target_time = sample_count * self.dt
            
            # Calculate actual elapsed time
            actual_elapsed = time.perf_counter() - start_perf_time
            
            # Sleep only until we reach the target time
            sleep_time = target_time - actual_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            
            # Get current time and check if we've exceeded experiment length
            current_time = time.perf_counter() - start_perf_time
            
            if current_time >= self.Exp_length_sec+0.5*self.dt:  # Added small buffer to ensure we capture the last sample
                display(f"Measurement completed after {current_time:.3f} seconds") # pyright: ignore[reportUndefinedVariable]
                break
            
            # Read data from the plant (only temperatures can be read)
            T1 = self.plant.read_t1()
            T2 = self.plant.read_t2()
            inputs = self.plant.read_inputs()  # Read all inputs (heater, fan, vane)
            row_data = [target_time, T1, T2] + inputs  # Create row data
            # Write data to CSV with the scheduled time (not actual elapsed time)
            self.writer.writerow([round(i, 3) for i in row_data])  # Round values for cleaner CSV
            self.file.flush()  # Ensure data is written to disk

            # print(f"Sample {sample_count}: Time: {target_time:.4f}s (drift: {(current_time - target_time)*1000:.2f}ms) | T1: {T1:.2f}°C | T2: {T2:.2f}°C")
            sample_count += 1
        

    def start(self):
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        self.file.close()

    def _on_stop_clicked(self, b):
        display("Measurement stopped prematurely.") # pyright: ignore[reportUndefinedVariable]
        self.stop()

    def _on_start_clicked(self, b):
        current_time = datetime.now().strftime("%H:%M")
        display(f"Measurement started at {current_time} for a duration of {self.Exp_length_sec/60} minutes") # pyright: ignore[reportUndefinedVariable]
        self.start()

# This class controls the animation in the live plot of the temperature signals (t1 and t2) from the plant.
class AnimateScope:
    def __init__(self, temp_lines, input_lines, temp_ax, input_ax, window_length=15, dt=0.1, plant=None, plant_model=None):
        # temp_lines: list of Line2D for temperatures
        # input_lines: list of Line2D for inputs
        self.temp_lines = temp_lines if isinstance(temp_lines, list) else [temp_lines]
        self.input_lines = input_lines if isinstance(input_lines, list) else [input_lines]
        self.temp_ax = temp_ax
        self.input_ax = input_ax
        self.dt = dt
        self.ptr = 0
        self.N = int(window_length / dt)
        self.temp_history = [np.zeros(self.N) for _ in range(len(self.temp_lines))]
        self.input_history = [np.zeros(self.N) for _ in range(len(self.input_lines))]
        self.plant = plant

        # Special procedure for plant model
        if plant_model is not None:
            self.X_sim = 0.0 # the internal simulation state
            if isinstance(plant_model, ct.TransferFunction):
                self.plant_model = ct.canonical_form(ct.tf2ss(plant_model), form='observable')[0] #Convert to observable canonical form
               
            elif isinstance(plant_model, ct.StateSpace):
                self.plant_model = plant_model
            else:
                TypeError("Plant has to be supplied as either ct.TransferFucntion or ct.StateSpace object")
            
            self.X0 = np.zeros(np.shape(self.plant_model.B)) # Initial condition of zeros, except current temperature which updates in the loop
            self.T_amb = 22.0 #Approximate temperature in the building


    # Initialize the plot with empty data and set the x-axis limits
    def init_plot(self):
        for line in self.temp_lines:
            line.set_ydata(np.empty(self.N))
        for line in self.input_lines:
            line.set_ydata(np.empty(self.N))
        return tuple(self.temp_lines + self.input_lines)
    
    # Update the history buffers with new temperature and input values, and return the current window of data for plotting
    def update_History(self, temp_vals, input_vals):
        # temp_vals, input_vals: arrays/lists
        if not isinstance(temp_vals, (list, np.ndarray)):
            temp_vals = [temp_vals]
        if not isinstance(input_vals, (list, np.ndarray)):
            input_vals = [input_vals]
        if isinstance(temp_vals, np.ndarray):
            temp_vals = temp_vals.flatten()
        if isinstance(input_vals, np.ndarray):
            input_vals = input_vals.flatten()
        for i, v in enumerate(temp_vals):
            if i < len(self.temp_history):
                self.temp_history[i][self.ptr] = v
        for i, v in enumerate(input_vals):
            if i < len(self.input_history):
                self.input_history[i][self.ptr] = v
        self.ptr = (self.ptr + 1) % self.N

        # Update animation windows by shifting the history bufffers forward in time
        temp_windows = []
        for i in range(len(self.temp_history)):
            y_full = np.concatenate((self.temp_history[i][self.ptr:], self.temp_history[i][:self.ptr]))
            y_window = y_full[-self.N:]
            temp_windows.append(y_window)
        input_windows = []
        for i in range(len(self.input_history)):
            y_full = np.concatenate((self.input_history[i][self.ptr:], self.input_history[i][:self.ptr]))
            y_window = y_full[-self.N:]
            input_windows.append(y_window)
        return temp_windows, input_windows

    # If a modeling function is definied, use the most recent input values to compute the modeled temperature at the current time step
    def simulate_plant_model(self, t, u_in):
        if self.plant_model is not None:
            # Get the most recent input values for the model (use the last value in the input history)
            t_solve = [t, t+self.dt]
            u_heater = u_in[0]
            sol = ct.forced_response(self.plant_model, t_solve, [u_heater, u_heater], self.X0/self.plant_model.C[0,0], return_x=True)
            self.X0 = sol.states[:,-1] 
            return self.plant_model.C @ self.X0 + self.T_amb # Return final temperature as simulation temp + ambient temp
        else:
            return None
        
    # Animation function called by FuncAnimation to update the plot at each frame.
    def animate(self, i):
        # Read current temperatures and inputs from the plant
        u_in = self.plant.read_inputs()  # Read all inputs (heater, fan

        T1 = self.plant.read_t1()
        T2 = self.plant.read_t2()

        if self.plant_model is not None:
            T_modeled = self.simulate_plant_model(i*self.dt, u_in)
            T_list = np.array([T1, T2, T_modeled])
        else:
            T_list = np.array([T1, T2])

        temp_windows, input_windows = self.update_History(T_list, u_in)
        x_window = np.linspace(i*self.dt, (i+len(temp_windows[0])-1)*self.dt, len(temp_windows[0]))
        # Update temperature lines
        for j, line in enumerate(self.temp_lines):
            if j < len(temp_windows):
                line.set_data(x_window, temp_windows[j])
        # Update input lines
        for j, line in enumerate(self.input_lines):
            if j < len(input_windows):
                line.set_data(x_window, input_windows[j])
        self.temp_ax.set_xlim(x_window[0], x_window[-1])
        self.input_ax.set_xlim(x_window[0], x_window[-1])
        return tuple(self.temp_lines + self.input_lines)