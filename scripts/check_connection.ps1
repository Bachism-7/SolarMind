param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$')]
    [string]$Alias
)

$ErrorActionPreference = "Stop"
$Ssh = Get-Command ssh -ErrorAction Stop
$RemoteCommand = "ros2 topic type /ros_robot_controller/bus_servo/set_position && ros2 topic info /ros_robot_controller/bus_servo/set_position && ros2 interface show ros_robot_controller_msgs/msg/ServosPosition"
& $Ssh.Source -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes $Alias $RemoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Read-only SSH diagnostics failed with exit code $LASTEXITCODE. No motion command was run."
}
