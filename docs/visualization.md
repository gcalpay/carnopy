# Scientific visualization

Carnopy visualization is a reproducible view of emitted dataset columns. It
does not call CoolProp or another thermodynamic backend, smooth curves,
interpolate property fields, extrapolate missing states, or fabricate phase
boundaries.

Install the alpha with visualization:

```bash
python -m pip install "carnopy[all]==0.1.0a1"
```

For repository development:

```bash
uv sync --locked --extra all --group dev
```

## Manual run workflow

When generation uses a custom output root, the run directory is created
directly beneath it:

```bash
carnopy generate \
  configs/cyclopentane_vapor_fraction_pressure.yaml \
  --out outputs/manual-test
```

Copy the exact path printed after `Output directory:`. Do not prepend the
output root a second time:

```bash
# Example only; replace this with the exact path printed by your run.
RUN_DIR="outputs/manual-test/20260621T172006Z_vapor_fraction_c8e28e9f"
```

## Plot kinds

Carnopy provides five explicit plot kinds:

```text
property-curves
property-heatmap
xy
pv
ts
```

The former `curves`, `heatmap`, and `contour` names are rejected with migration
guidance. Contours are deliberately unsupported because contour rendering
interpolates between sampled thermodynamic states.

| Dataset mode | property curves | property heatmap | x-y | p-v | T-s |
|---|---:|---:|---:|---:|---:|
| `property_table` | yes | yes | yes | yes | yes |
| `saturation_table` | yes | no | yes | yes | yes |
| `vapor_mass_fraction_table` | yes | yes | yes | yes | yes |

## Property curves

Curves use discrete, colorblind-safe series colors, deterministic dash styles,
and markers at every valid emitted sample. Straight segments only show
connectivity between adjacent valid samples. Lines break at invalid or missing
samples and at property-table phase changes.

For a `property_table`, choose the x-axis explicitly. The other configured
coordinate defines the curve family:

```bash
carnopy plot outputs/<property-run> \
  --kind property-curves \
  --property mass_density \
  --x temperature
```

This produces mass density versus temperature with one series per sampled
pressure. Use `--x pressure` for one series per sampled temperature.

For a `saturation_table`, Carnopy plots separate saturated-liquid and
saturated-vapor branches against the sampled saturation coordinate. It never
connects the two endpoints at one coordinate or fabricates a saturation dome.

For a `vapor_mass_fraction_table`, vapor mass fraction is the x-axis and the
sampled saturation pressure or temperature defines the series:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-curves \
  --property mass_density \
  --value-scale linear \
  --show
```

Use `--value-scale log` only when every plotted property value is positive.
Carnopy never changes the requested scale automatically. A large positive
linear range produces an advisory in the CLI output and `.plot.json`.

## Sampled property heatmaps

Heatmaps use flat, non-interpolated cells centered on emitted coordinate pairs.
Cell boundaries come from adjacent coordinate midpoints. Missing and invalid
cells remain masked, and sample markers show where dataset rows exist.

For `property_table`:

```text
x = temperature
y = pressure
color = selected property
```

For `vapor_mass_fraction_table`:

```text
x = vapor mass fraction
y = sampled saturation pressure or temperature
color = selected property
```

Example:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-heatmap \
  --property specific_enthalpy \
  --color-scale linear \
  --output figures/cyclopentane-enthalpy-map.pdf
```

Heatmaps require at least two unique values on both axes. Duplicate coordinate
pairs are rejected rather than aggregated. `saturation_table` is rejected
because it contains only the sampled `q=0` and `q=1` endpoint states; generate a
`vapor_mass_fraction_table` for a quality-resolved sampled map.

Use `--color-scale log` only when every plotted property value is positive.

## Generic x-y plots

`xy` plots two numeric semantic fields from emitted data:

```bash
carnopy plot "$RUN_DIR" \
  --kind xy \
  --x specific_enthalpy \
  --y vapor_mass_fraction
```

Available numeric axes include temperature, pressure, vapor mass fraction,
requested properties, and `specific_volume`. The only derived field is:

```text
specific_volume = 1 / mass_density
```

It requires emitted, finite, positive mass density. Categorical fields such as
phase and saturation endpoint may group or filter series but cannot be numeric
axes.

Carnopy determines path ordering and grouping from the independent sampling
coordinates:

- If no sampling coordinate varies, samples are rendered as isolated markers.
- If exactly one varies, it determines the path order for one sampled series.
- If one axis sampling coordinate and one non-axis sampling coordinate vary,
  the non-axis coordinate is the unambiguous series grouping.
- Otherwise, select a grouping with `--group-by`; each group may retain at most
  one varying path coordinate.

For example, enthalpy versus entropy in a temperature-pressure table is
ambiguous until the user chooses isobars or isotherms:

```bash
carnopy plot outputs/<property-run> \
  --kind xy \
  --x specific_enthalpy \
  --y specific_entropy \
  --group-by pressure
```

After grouping, at most one unresolved sampling coordinate may remain.
Carnopy rejects ambiguous requests rather than applying a hidden precedence.
Saturation-table x-y plots always keep saturated-liquid and saturated-vapor
branches separate.

## p-v diagrams

The `pv` kind has fixed SI axes:

```text
x = specific volume, v [m³ kg⁻¹]
y = pressure, p [Pa]
```

It requires emitted mass density and pressure:

```bash
carnopy plot outputs/<run-with-density> \
  --kind pv
```

Mode behavior:

- `property_table`: one sampled isotherm per configured temperature;
- `saturation_table`: separate sampled liquid and vapor endpoint branches;
- `vapor_mass_fraction_table`: one quality line per sampled saturation
  coordinate, plus sampled `q=0` and `q=1` boundary branches when available.

Carnopy never extrapolates a saturation dome or critical point.

## T-s diagrams

The `ts` kind has fixed SI axes:

```text
x = specific entropy, s [J kg⁻¹ K⁻¹]
y = temperature, T [K]
```

It requires emitted specific entropy, emitted temperature, and dataset metadata
containing the reference-state policy:

```bash
carnopy plot outputs/<run-with-entropy> \
  --kind ts
```

Mode behavior:

- `property_table`: one sampled isobar per configured pressure;
- `saturation_table`: separate sampled liquid and vapor endpoint branches;
- `vapor_mass_fraction_table`: one quality line per sampled saturation
  coordinate, plus available sampled endpoint branches.

The figure footer and `.plot.json` preserve the entropy reference-state policy.
Standalone files without this metadata are rejected because absolute entropy
cannot be interpreted safely without the recorded convention.

Both p-v and T-s default to linear axes. Logarithmic axes are explicit:

```bash
carnopy plot outputs/<run> \
  --kind pv \
  --x-scale log \
  --y-scale log
```

Logarithmic axes require every relevant plotted value to be positive. Carnopy
does not switch scales automatically.

## Exact filters and fluids

Numeric filters use canonical SI values and never select a nearest neighbor:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-curves \
  --property mass_density \
  --filter pressure=200000
```

Repeat `--filter` to combine exact filters with logical AND. Current filters are
temperature, pressure, vapor mass fraction, phase, and saturation endpoint.

When a source contains multiple fluids, select one or more explicitly:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-curves \
  --property mass_density \
  --fluid n-Propane \
  --fluid IsoButane
```

Repeat `--fluid` to create one comparable facet per selected fluid. Heatmap
facets share one property color normalization. Use the canonical fluid names
shown in the dataset or by `carnopy fluids`.

## Sources and display units

`SOURCE` may be a run directory, CSV, or Parquet file. Run directories prefer
Parquet, verify it against `metadata.json`, preserve sampler order, and use the
original configured pressure or temperature display unit.

Standalone files are unverified. `property_table` files contain enough
coordinate semantics for current plots. Standalone saturation and
vapor-mass-fraction files require:

```bash
--saturation-coordinate pressure
```

or:

```bash
--saturation-coordinate temperature
```

when no sibling metadata is available. A value conflicting with metadata is an
error.

Existing long-form run-directory names remain readable because plotting
identifies runs from their contents, not their directory names.

## Python API

```python
from carnopy.visualization import (
    plot_dataset,
    plot_property_curves,
    plot_property_heatmap,
    plot_thermodynamic_diagram,
    plot_xy,
)

curves = plot_property_curves(
    "outputs/<run>",
    property_name="mass_density",
)

heatmap = plot_property_heatmap(
    "outputs/<run>",
    property_name="mass_density",
)

same_heatmap = plot_dataset(
    "outputs/<run>",
    kind="property-heatmap",
    property_name="mass_density",
)

xy = plot_xy(
    "outputs/<run>",
    x="specific_enthalpy",
    y="vapor_mass_fraction",
)

pv = plot_thermodynamic_diagram("outputs/<run>", kind="pv")
ts = plot_thermodynamic_diagram("outputs/<run>", kind="ts")
```

Each result contains the exported image path, sidecar path, source identity,
selected fluids, sample counts, effective settings, and advisories. The
returned Matplotlib figure represents an image that has already been exported.
Changing it does not update the image or sidecar.

## Export integrity

Every export writes an image and `.plot.json` sidecar outside the immutable
source run. Existing image or sidecar paths are refused, so repeated manual
tests need a new filename.

Finalization uses exclusive same-filesystem hard links. This prevents
concurrent overwrite races. The two-file pair is not fully crash-atomic:
abrupt process termination between links can leave an image without its
sidecar.

All plot kinds remain derived exclusively from emitted dataset columns.
