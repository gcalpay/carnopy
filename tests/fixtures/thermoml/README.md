# ThermoML parser qualification fixtures

`density.xml` and `density.json` are independently hand-authored synthetic
examples for Carnopy's supported ThermoML subset. They are not measurements,
published records, or full-XSD conformance fixtures. The component names and
DOI are fictional test identifiers. No archive payload is vendored here.

The pair contains a pure-component series with a repeated density measurement,
a binary series with a reported liquid mole fraction, variable pressure,
constraint temperature, explicit samples, method evidence, and expanded
uncertainty with confidence level but no coverage factor. JSON keys deliberately
use a different order; `tml_elements` retains scientific element order. Numeric
tokens include trailing zeroes to test lossless evidence parsing.

Tests mutate copies in temporary directories to exercise malformed identifiers,
references, qualifiers, numbers, composition, selections, resource bounds, and
source changes. Real NIST qualification remains explicit, hash-recorded, and
outside routine offline CI; see `SOURCE_IMPORT_PLAN.md`.
