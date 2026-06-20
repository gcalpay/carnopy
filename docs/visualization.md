# Scientific visualization

Visualization is optional and currently supports
`vapor_mass_fraction_table` datasets.

Install:

```bash
python -m pip install -e ".[viz]"
```

Curves show the selected property against vapor mass fraction, with one sampled
line per pressure or temperature:

```bash
carnopy plot outputs/<run> \
  --property mass_density \
  --kind curves \
  --show
```

Contours show the full sampled response surface:

```bash
carnopy plot outputs/<run> \
  --property specific_enthalpy \
  --kind contour \
  --output figures/cyclopentane_enthalpy.pdf
```

The source may be a run directory, CSV, or Parquet file. Run directories prefer
Parquet and verify the dataset against `metadata.json`. Standalone files without
metadata require `--coordinate pressure` or `--coordinate temperature` and are
marked unverified.

Only valid rows are plotted. Missing or invalid samples remain gaps; curves are
not smoothed and contours do not extrapolate across masked cells. Linear scaling
is the default. `--scale log` is explicit and rejected for nonpositive values.

When a dataset contains multiple pure fluids, pass one or more repeatable
`--fluid` options. Multiple selections are rendered as comparable facets rather
than overlaid.

Every export writes an image and a `.plot.json` provenance sidecar under
`figures/` by default. The immutable generation run is never modified.

Python callers can customize the returned Matplotlib figure:

```python
from carnopy.visualization import plot_dataset

result = plot_dataset(
    "outputs/<run>",
    property_name="mass_density",
    kind="contour",
)
result.figure.suptitle("Cyclopentane density response")
```
