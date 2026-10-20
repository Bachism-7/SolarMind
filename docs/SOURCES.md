# Source notes

These sources document software behavior and interfaces. They do not verify calibration, travel, ROS topic subscribers, or the modified JetArm hardware.

- [pvlib solar position API](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.solarposition.get_solarposition.html) documents timezone-aware pandas timestamps and the NREL SPA implementation used by SolarMind.
- [pvlib solar-position overview](https://pvlib-python.readthedocs.io/en/stable/reference/solarposition.html) describes the available solar position functions.
- [ROS 2 `ros2 topic pub` source](https://github.com/ros2/ros2cli/blob/rolling/ros2topic/ros2topic/verb/pub.py) is a reference for the one-shot CLI behavior. The installed Jetson ROS CLI still must be checked read-only.
- [MDN Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition) documents browser geolocation permission and position retrieval.
- [Python on Windows](https://docs.python.org/3/using/windows.html) documents the Windows Python launcher and virtual environments.

SolarMind does not call these websites or a geocoding service while running. Solar position is calculated locally after dependencies are installed.
