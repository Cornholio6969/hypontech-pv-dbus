# dbus-hypon-pv

Hypontech Cloud integration for Victron Venus OS.

The service polls a Hypon Cloud plant and publishes the inverter on D-Bus as a
Victron PV inverter. It is intended for Cerbo GX, Ekrano GX and other Venus OS
devices where the inverter is not connected directly to the GX device.

## Features

- Registers as `com.victronenergy.pvinverter.hypon_<device instance>`
- Reports current PV production and accumulated energy
- Supports one-phase and three-phase installations
- Configurable AC position, device instance and inverter capacity
- Re-authenticates when the Hypon session expires
- Keeps running through temporary cloud or network failures
- Starts automatically after a Venus OS reboot or firmware update
- Uses only Python modules already available on Venus OS

## Requirements

- A Venus OS device with SSH access
- Hypon Cloud account credentials
- The plant/system ID from Hypon Cloud
- Internet access from the GX device

## Installation

Copy the repository to `/data/etc` on the GX device:

```sh
scp -r dbus-hypon-pv root@VENUS_IP:/data/etc/
ssh root@VENUS_IP
```

Create the local configuration:

```sh
cd /data/etc/dbus-hypon-pv
cp config.example.ini config.ini
vi config.ini
```

Set these values:

```ini
[HYPON]
username = user@example.com
password = your-password
system_id = 2005739684641611776
```

Install and start the service:

```sh
sh install.sh
```

When `install.sh` creates `config.ini` for you, edit the file and then run:

```sh
sh restart.sh
```

## Configuration

The most commonly changed settings are:

```ini
[DEFAULT]
device_name = Hypontech PV
device_instance = 51

[PV]
position = 0
max_power = 6000

[HYPON]
refresh_time = 30

[MAPPING]
phase_count = 1
```

### AC position

| Value | Victron position |
| ---: | --- |
| `0` | AC input 1 |
| `1` | AC output |
| `2` | AC input 2 |

Choose the position that matches the physical connection of the inverter. This
affects how Venus OS includes the PV production in its system calculations.

### Three-phase systems

Set:

```ini
[MAPPING]
phase_count = 3
```

When Hypon only returns total AC power, the service divides it evenly between
the configured phases. If the API returns separate phase values such as
`power_l1`, `power_l2` and `power_l3`, those values are used instead.

### Unit conversion

The default Hypon values are expected to be watts and kWh. Multipliers can be
used when an account returns different units:

```ini
[MAPPING]
power_multiplier = 1
energy_multiplier = 1
```

For example, use `energy_multiplier = 0.001` when the total energy value is
reported in Wh.

## Logs and service control

Follow the log:

```sh
tail -f /data/log/dbus-hypon-pv/current
```

Check the service:

```sh
svstat /service/dbus-hypon-pv
```

Restart it:

```sh
sh /data/etc/dbus-hypon-pv/restart.sh
```

Stop it:

```sh
svc -d /service/dbus-hypon-pv
```

Start it:

```sh
svc -u /service/dbus-hypon-pv
```

Run the Python process directly when troubleshooting startup errors:

```sh
cd /data/etc/dbus-hypon-pv
/usr/bin/python3 -u dbus-hypon-pv.py
```

## D-Bus values

The service publishes, among others:

| Path | Description |
| --- | --- |
| `/Ac/Power` | Current total AC production |
| `/Ac/Current` | Current total AC current |
| `/Ac/Voltage` | AC voltage |
| `/Ac/Energy/Forward` | Lifetime generated energy |
| `/Ac/Energy/Today` | Energy generated today |
| `/Ac/L1/Power` | Phase 1 power |
| `/Ac/L2/Power` | Phase 2 power |
| `/Ac/L3/Power` | Phase 3 power |
| `/Connected` | Cloud data is current |
| `/StatusCode` | Victron inverter state |
| `/ErrorCode` | Driver communication state |

A full path overview is available in [docs/dbus-paths.md](docs/dbus-paths.md).

## Updating

Keep your local `config.ini`, replace the remaining repository files and run:

```sh
sh install.sh
sh restart.sh
```

`config.ini` is ignored by Git to prevent credentials from being committed.

## Uninstalling

```sh
sh /data/etc/dbus-hypon-pv/uninstall.sh
```

The uninstall script removes the service registration. It leaves the repository,
configuration and logs in place.

## Notes

Hypon Cloud is an undocumented private API. The current defaults use:

```text
POST /v2/login
GET  /v2/plant/{system_id}/monitor?refresh=true
```

The endpoints, authentication header and JSON field mappings remain
configurable in `config.ini` in case Hypon changes the API.

Cloud polling also means the values can be delayed compared with a direct
RS485, Modbus or MQTT connection.

## Credits

The project was inspired by:

- `amckee23/home-assistant-hypon-cloud`
- `mr-manuel/venus-os_dbus-mqtt-pv`

## License

Released under the MIT License.
