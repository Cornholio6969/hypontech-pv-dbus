# D-Bus paths

The service registers as:

```text
com.victronenergy.pvinverter.hypon_<device_instance>
```

## Identification

| Path | Value |
| --- | --- |
| `/DeviceInstance` | Configured Victron device instance |
| `/ProductId` | `0xFFFF` |
| `/ProductName` | `Hypon Cloud PV Inverter` |
| `/CustomName` | Configured device name |
| `/FirmwareVersion` | Driver version |
| `/Mgmt/Connection` | `Hypon Cloud REST API` |

## System integration

| Path | Description |
| --- | --- |
| `/Position` | Legacy PV inverter position |
| `/Ac/Position` | AC input/output position |
| `/Ac/MaxPower` | Nominal inverter power |
| `/Connected` | `1` while fresh cloud data is available |
| `/StatusCode` | `7` running, `8` standby, `0` unavailable |
| `/ErrorCode` | `0` normal, `1` communication timeout |
| `/UpdateIndex` | Incremented after every successful update |

## Measurements

| Path | Unit |
| --- | --- |
| `/Ac/Power` | W |
| `/Ac/Current` | A |
| `/Ac/Voltage` | V |
| `/Ac/Energy/Forward` | kWh |
| `/Ac/Energy/Today` | kWh |
| `/Ac/L1/Power` | W |
| `/Ac/L1/Current` | A |
| `/Ac/L1/Voltage` | V |
| `/Ac/L1/Frequency` | Hz |
| `/Ac/L2/...` | Same values for phase 2 |
| `/Ac/L3/...` | Same values for phase 3 |
