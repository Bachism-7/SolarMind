"""SolarMind serial settings.

Copy this file to `serial_login.py` (same folder) and edit it. `serial_login.py` is
git-ignored so your credentials are never committed. It is re-read on every request,
so changes apply without restarting the server.

SolarMind talks to the Jetson/robot directly over the serial port, so PuTTY is not
needed. Only one program can hold a COM port at a time: close PuTTY before sending.
"""

# --- Serial port ------------------------------------------------------------
PORT = "COM7"          # default port; the web page can override it
BAUDRATE = 115200

# --- Login credentials (leave USERNAME empty if the port is already logged in) --
USERNAME = "your-username"
PASSWORD = "your-password"

# --- How to recognise the device's prompts (regular expressions) ------------
LOGIN_PROMPT = r"login:\s*$"
PASSWORD_PROMPT = r"[Pp]assword:\s*$"
SHELL_PROMPT = r"[$#]\s*$"

# --- Optional line run once after login, e.g. to load ROS 2 -----------------
ROS_SETUP = ""         # e.g. "source /opt/ros/humble/setup.bash"

# --- Timing (seconds) -------------------------------------------------------
LOGIN_TIMEOUT = 20
COMMAND_TIMEOUT = 25

# --- Servos and calibration (verify on the real hardware before trusting) ---
AZIMUTH_SERVO_ID = 1
TILT_SERVO_ID = 10
AZIMUTH_MIN_PULSE = 0
AZIMUTH_MAX_PULSE = 1000
TILT_MIN_PULSE = 0
TILT_MAX_PULSE = 1000
TILT_DIRECTION = 1       # 1 or -1: flips the tilt direction
TILT_OFFSET_DEG = 0.0    # added to the panel tilt before converting to a pulse
