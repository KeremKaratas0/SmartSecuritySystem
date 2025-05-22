#!/usr/bin/expect -f
log_user 1
set timeout 30
set mac_address MAC

spawn bluetoothctl
expect "#"
send "power on\r"
expect "#"
send "agent on\r"
expect "#"
send "default-agent\r"
expect "#"
send "discoverable on\r"
send "scan on\r"
sleep 2

set device_found 0
while {!$device_found} {
    expect {
        -re "$mac_address.*" {
            set device_found 1
            send_user "found device"
        }
        timeout {
            puts "Still scanning..."
            send "\r"
        }
    }
}

send "scan off\r"
expect "#"
send "pair $mac_address\r"
expect {
  -re {\[agent\] Confirm passkey [0-9]+ \(yes/no\):} {
    send "yes\r"
  }
  timeout {
    send_user "Timed out waiting for passkey confirmation\n"
    exit 1
  }
}
sleep 1

send "trust $mac_address\r"
expect {
  "trust succeeded" {
    send_user "Device trusted.\n"
  }
  timeout {
    send_user "Timed out while trusting device.\n"
    exit 1
  }
}
sleep 1
send "connect $mac_address\r"
expect {
  "Connection successful" {
    send_user "Device connected.\n"
  }
  timeout {
    send_user "Timed out while connecting device.\n"
    exit 1
  }
}