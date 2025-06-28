# Temperature Presets Configuration

The printer dashboard supports custom temperature presets that can be configured in your `options.json` file. This allows you to define quick-access temperature buttons for extruder, bed, and chamber heaters.

## Configuration

Add a `temperature_presets` section to your `options.json` configuration file:

```json
{
  "printers": [
    // ... your printer configurations
  ],
  "temperature_presets": {
    "extruder": [0, 180, 200, 215, 220, 230, 250, 260],
    "bed": [0, 50, 60, 70, 80, 90, 100, 110],
    "chamber": [0, 35, 40, 45, 50, 60, 70, 80]
  }
}
```

## Heater Types

### `extruder`
Temperature presets for extruder/hotend heating. Common values:
- **0**: Turn off heater
- **180-200**: PLA printing temperatures
- **220-250**: PETG printing temperatures 
- **250-280**: ABS printing temperatures

### `bed`
Temperature presets for heated bed. Common values:
- **0**: Turn off bed heater
- **50-60**: PLA bed temperatures
- **70-80**: PETG bed temperatures
- **80-110**: ABS bed temperatures

### `chamber`
Temperature presets for chamber heating (if your printer has a heated chamber). Common values:
- **0**: Turn off chamber heater
- **35-45**: Basic chamber warming
- **50-80**: Advanced chamber heating for ABS/ASA

## Default Presets

If no `temperature_presets` are configured, the following defaults are used:

```json
{
  "extruder": [0, 200, 220, 250],
  "bed": [0, 60, 80, 100],
  "chamber": [0, 40, 60, 80]
}
```

## Usage

1. **Click any temperature display** on a printer card (extruder, bed, or chamber)
2. **Select from preset buttons** or manually enter a temperature
3. **Click "Set Temperature"** to apply the new target temperature

## Features

- ✅ **Customizable per heater type** - Different presets for extruder, bed, and chamber
- ✅ **Unlimited presets** - Add as many temperature values as needed
- ✅ **Auto-sorting** - Preset buttons are displayed in the order you define them
- ✅ **Fallback defaults** - System uses sensible defaults if configuration is missing
- ✅ **Dynamic loading** - Changes take effect after restarting the dashboard

## Examples

### Basic Configuration
```json
"temperature_presets": {
  "extruder": [0, 200, 220],
  "bed": [0, 60, 80],
  "chamber": [0, 40]
}
```

### Advanced Multi-Material Configuration
```json
"temperature_presets": {
  "extruder": [0, 180, 200, 215, 220, 230, 240, 250, 260, 280],
  "bed": [0, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 100, 110],
  "chamber": [0, 30, 35, 40, 45, 50, 55, 60, 65, 70]
}
```

### PLA-Only Printer
```json
"temperature_presets": {
  "extruder": [0, 185, 195, 205, 215],
  "bed": [0, 50, 55, 60, 65],
  "chamber": [0]
}
```

## Notes

- Temperature values should be integers (whole numbers)
- Include `0` to provide an "Off" button
- Values are displayed in the order you specify them
- Changes require restarting the printer dashboard to take effect
- Each heater type can have different numbers of presets 