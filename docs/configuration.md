# Configuration

Generate a commented template:

```bash
carnopy init property_table my-dataset.yaml
```

Use `carnopy fluids` and `carnopy properties` to discover accepted semantic
names. `carnopy generate` validates automatically; `carnopy validate` is an
optional standalone check.

Schema version 1 requires:

```yaml
schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane]
grid:
  temperature:
    kind: linspace
    start: 20
    stop: 100
    num: 5
    unit: degC
  pressure:
    kind: geomspace
    start: 1
    stop: 20
    num: 5
    unit: bar
properties:
  - specific_enthalpy
  - mass_density
```

## Sampling

- `explicit`: ordered `values`.
- `linspace`: inclusive `start`, `stop`, and `num`.
- `stepspace`: inclusive `start`, `stop`, and constant `step`; the endpoint
  must be exactly reachable within documented numerical tolerance.
- `geomspace`: positive physical endpoints and `num`.
- `logspace`: exponent bounds, `num`, and optional `base`.

Bounded samplers support ascending and descending ranges. Equal bounds are
rejected; use `explicit` for one value. Geometric/logarithmic sampling is not
allowed for `degC` or vapor mass fraction.

## Units

- Temperature: `K`, `degC`
- Pressure: `Pa`, `kPa`, `MPa`, `bar`
- Vapor mass fraction: `"1"`

## Modes

`property_table` requires temperature and pressure.

`saturation_table` requires exactly one of temperature or pressure and emits
separate saturated-liquid and saturated-vapor rows.

`vapor_mass_fraction_table` requires vapor mass fraction plus exactly one of
temperature or pressure. Vapor mass fraction is the mass of vapor divided by
total vapor-plus-liquid mass. CoolProp's `Q` notation remains internal.

Validation proves that the configuration is structurally executable. It does
not promise that every fluid/state/property combination will be valid.
