# Scientific visualization

Visualization is optional and currently supports
`vapor_mass_fraction_table` datasets.

Install the alpha with visualization:

```bash
python -m pip install "carnopy[all]==0.1.0a1"
```

For repository development:

```bash
uv sync --locked --extra all --group dev
```

## Curves and contours

Curves show one sampled line per configured pressure or temperature:

```bash
carnopy plot outputs/<run> \
  --property mass_density \
  --kind curves \
  --show
```

Contours show the sampled response surface:

```bash
carnopy plot outputs/<run> \
  --property specific_enthalpy \
  --kind contour \
  --output figures/cyclopentane_enthalpy.pdf
```

Invalid samples remain gaps. Curves are not smoothed, and contour corner filling
is disabled so masked states are not rendered as valid data.

Linear scaling is the default. `--scale log` is explicit and requires every
plotted value to be positive.

## Sources and fluids

`SOURCE` may be a run directory, CSV, or Parquet file. Run directories prefer
Parquet and verify it against `metadata.json`. Standalone files without metadata
require `--coordinate pressure` or `--coordinate temperature` and are marked
unverified.

For multiple pure fluids, repeat `--fluid`:

```bash
carnopy plot outputs/<run> \
  --property mass_density \
  --fluid Propane \
  --fluid Isobutane
```

Each selected fluid receives its own comparable facet.

## Export integrity

Every export writes an image and `.plot.json` sidecar outside the immutable
source run. Existing image or sidecar paths are refused.

Finalization uses exclusive same-filesystem hard links. This prevents concurrent
overwrite races. The two-file pair is not fully crash-atomic: abrupt process
termination between links can leave an image without its sidecar.

Python API:

```python
from carnopy.visualization import plot_dataset

result = plot_dataset(
    "outputs/<run>",
    property_name="mass_density",
    kind="contour",
)
```

`result.figure` represents an image that has already been exported. Later
Matplotlib changes do not update the image or sidecar; call `plot_dataset` again
with a new output path to create another traceable export.
