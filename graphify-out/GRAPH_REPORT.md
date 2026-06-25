# Graph Report - /home/cfd/carnopy  (2026-06-25)

## Corpus Check
- 138 files · ~69,856 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1147 nodes · 3494 edges · 67 communities (55 shown, 12 thin omitted)
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 694 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]

## God Nodes (most connected - your core abstractions)
1. `generate_dataset()` - 110 edges
2. `ConfigError` - 67 edges
3. `VisualizationError` - 62 edges
4. `PlotSource` - 57 edges
5. `get_field()` - 56 edges
6. `PlotRequest` - 54 edges
7. `OutputError` - 46 edges
8. `CoolPropBackend` - 44 edges
9. `load_plot_source()` - 31 edges
10. `plot_property_curves()` - 30 edges

## Surprising Connections (you probably didn't know these)
- `test_backend_qualifies_calls_and_reference_targets()` --calls--> `CoolPropBackend`  [INFERRED]
  tests/test_coolprop_models.py → src/carnopy/backends/coolprop.py
- `test_dynamic_range_advisory_never_changes_scale()` --calls--> `dynamic_range_advisories()`  [INFERRED]
  tests/test_visualization_foundation.py → src/carnopy/visualization/selection.py
- `Vapor Mass Fraction` --semantically_similar_to--> `Dataset Modes`  [INFERRED] [semantically similar]
  README.md → AGENTS.md
- `Model Sweeps` --semantically_similar_to--> `Model Sweep Contract`  [INFERRED] [semantically similar]
  README.md → AGENTS.md
- `ML Preparation Foundation` --semantically_similar_to--> `Preparation Contract`  [INFERRED] [semantically similar]
  README.md → AGENTS.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Dataset Generation Contracts** — agents_yaml_schema_version_2, agents_coolprop_models, agents_dataset_modes, agents_provenance_identities, readme_generated_outputs_and_provenance [EXTRACTED 1.00]
- **Release and Verification Pipeline** — github_contributing_quality_checks, workflows_ci_verify_workflow, workflows_ci_distribution_verification, workflows_publish_publish_verified_distributions, agents_release_safeguards [INFERRED 0.85]
- **Starter Configurations** — templates_property_table_property_table_starter_template, templates_saturation_table_saturation_table_starter_template, templates_model_sweep_model_sweep_starter_template, templates_preparation_preparation_starter_template, templates_full_reference_carnopy_configuration_reference [EXTRACTED 1.00]

## Communities (67 total, 12 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (73): DataFrame, DerivedFeature, ConfigError, Configuration or normalization failed before generation., FieldKind, PartitionName, derived_definition(), DerivedFeatureDefinition (+65 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (69): ArrayFormat, PreparationResult, datetime, OutputError, Run artifacts could not be finalized., ndarray, create_run_layout(), finalize_run_layout() (+61 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (28): Any, PropertyBackend, __getattr__(), BackendResult, normalize_phase(), PropertyDefinition, FailureLayer, assign_case_ids() (+20 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (39): _child_directories(), _comparison_plot_snippet(), _delta_reason_counts(), _delta_summaries(), _indent(), _inspect_preparation_bundle(), inspect_source(), _inspect_sweep_bundle() (+31 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (33): ModuleType, Path, property_config_path(), saturation_config_path(), vapor_config_path(), test_generate_creates_output(), test_help_and_version_do_not_load_scientific_dependencies(), test_init_creates_packaged_template_and_prints_workflow() (+25 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (44): Argument, callback, ConfigModeCli, CoolPropModelCli, _echo_preparation_reference_advisory(), fluids_command(), generate_command(), init_command() (+36 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (17): BaseModel, OutputConfig, ComparisonPlotConfig, ComparisonPlotsConfig, ModelSweepConfig, SweepBackendConfig, VisualizationPlotConfig, DatasetFormat (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (35): FilterValue, PlotFormat, SaturationCoordinate, test_filter_identity_canonicalizes_equivalent_values(), test_numeric_filter_uses_tolerance_without_nearest_selection(), test_request_identity_expands_defaults_and_preserves_order(), test_selection_applies_numeric_and_categorical_filters(), ValidationInfo (+27 more)

### Community 8 - "Community 8"
Cohesion: 0.17
Nodes (36): prepare_dataset(), load_preparation_config(), _grid_property_config(), _prep_config(), _prep_config_with_scenarios(), _property_config(), _relative_files(), _sweep_config() (+28 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (29): convert_axis_values_to_si(), UnitDefinition, validate_axis_unit(), PlotCoordinate, test_engineering_units_convert_to_si(), test_invalid_unit_and_physical_values_fail(), test_all_milestone_modes_are_valid_plot_sources(), test_csv_only_run_is_a_verified_plot_source() (+21 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (23): _axis_metadata(), _curve_fields(), _display_values(), _format_value(), _level_mask(), _ordered_levels(), _reference_dependent(), render_property_curves() (+15 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (31): CoolProp Models, Dataset Modes, Milestone 1 Scope, Model Sweep Contract, Preparation Contract, Provenance Identities, Visualization Contracts, YAML Schema Version 2 (+23 more)

### Community 12 - "Community 12"
Cohesion: 0.19
Nodes (28): generate_dataset(), MonkeyPatch, test_dispatch_rejects_plot_kind_specific_options_instead_of_ignoring_them(), test_exact_filter_is_recorded_and_limits_curve_family(), test_existing_plot_artifact_is_preserved(), test_external_image_created_after_precheck_is_not_overwritten(), test_invalid_rows_remain_curve_gaps(), test_legacy_plot_kinds_are_rejected_with_migration_guidance() (+20 more)

### Community 13 - "Community 13"
Cohesion: 0.14
Nodes (27): generate_model_sweep(), load_sweep_config_file(), ConfigTemplateMode, initialize_config(), A starter configuration cannot be created safely., Return the packaged starter configuration for one template type., Create one configuration from a packaged template without overwriting., template_text() (+19 more)

### Community 14 - "Community 14"
Cohesion: 0.21
Nodes (27): PlotScale, SeriesInput, Advisory, PlotResult, A visualization request cannot be completed safely., Optional visualization dependencies are unavailable., RenderedPlot, VisualizationDependencyError (+19 more)

### Community 15 - "Community 15"
Cohesion: 0.15
Nodes (22): Hash a file without loading the complete artifact into memory., sha256_file(), VisualizationSummary, VisualizationConfig, _delta_ylabel(), _field_column(), _float_equal(), _metric_summary() (+14 more)

### Community 16 - "Community 16"
Cohesion: 0.22
Nodes (25): render_thermodynamic_diagram(), _thermodynamic_group_field(), _thermodynamic_path_field(), _thermodynamic_series(), _vapor_quality_series(), PlotSource, axis_metadata(), _canonical_level() (+17 more)

### Community 17 - "Community 17"
Cohesion: 0.15
Nodes (20): __getattr__(), build_identity(), build_output_request_id(), Identity, identity_dict(), runtime_versions(), sha256_bytes(), canonical_json_bytes() (+12 more)

### Community 18 - "Community 18"
Cohesion: 0.13
Nodes (13): Message, Protocol, distribution_paths(), DistributionReader, forbidden_paths(), inspect_sdist(), inspect_wheel(), main() (+5 more)

### Community 19 - "Community 19"
Cohesion: 0.16
Nodes (16): Sampler, materialize_sampler(), _materialize_stepspace(), ExplicitSampler, GeomspaceSampler, _is_finite(), LinspaceSampler, LogspaceSampler (+8 more)

### Community 20 - "Community 20"
Cohesion: 0.13
Nodes (6): CoolPropBackend, test_backend_lists_and_canonicalizes_fluids(), test_backend_property_and_phase_calls_work(), test_backend_rejects_unknown_model(), test_cubic_backend_lists_only_model_supported_fluids(), test_reference_state_is_initialized_once_per_fluid()

### Community 21 - "Community 21"
Cohesion: 0.17
Nodes (15): load_config(), load_config_file(), _load_yaml_mapping(), LoadedConfig, normalize_config(), _projected_rows(), _stable_float(), _stable_value() (+7 more)

### Community 22 - "Community 22"
Cohesion: 0.18
Nodes (13): validate_config(), test_public_api(), test_dataset_formats_are_canonical_and_validated(), test_expanded_row_limit_is_enforced(), test_invalid_vapor_mass_fraction_fails(), test_schema_version_one_fails_with_concise_migration_message(), test_valid_example_config(), test_all_models_generate_all_dataset_modes() (+5 more)

### Community 23 - "Community 23"
Cohesion: 0.24
Nodes (15): _generate_rows(), _input_columns(), run_generation(), _sample_index(), _saturation_axis(), _stable_float_key(), _state_key(), validate_loaded_config() (+7 more)

### Community 24 - "Community 24"
Cohesion: 0.21
Nodes (11): LoadedSweepConfig, BackendConfig, CarnopyConfig, normalize_sweep_config(), NormalizedSweep, _child_result_dict(), _fluid_aliases(), run_model_sweep() (+3 more)

### Community 25 - "Community 25"
Cohesion: 0.20
Nodes (16): dtype, float64, _split_phase_changes(), _axis_metadata(), _cell_boundaries(), _display_series(), _heatmap_fields(), _reference_dependent() (+8 more)

### Community 26 - "Community 26"
Cohesion: 0.21
Nodes (15): test_diagram_invalid_sample_remains_a_gap(), test_diagram_log_scale_rejects_nonpositive_axis_values(), test_fixed_diagram_dispatch_rejects_custom_axes(), test_pv_property_table_uses_exact_reciprocal_density_and_isotherms(), test_saturation_diagrams_keep_liquid_and_vapor_branches_separate(), test_saturation_xy_keeps_endpoint_branches_separate(), test_standalone_vapor_diagram_accepts_explicit_saturation_coordinate(), test_ts_property_table_uses_emitted_entropy_and_reference_policy() (+7 more)

### Community 27 - "Community 27"
Cohesion: 0.22
Nodes (13): _build_sidecar(), _ensure_output_outside_source_run(), export_figure(), _hash_file(), _metadata_text(), _plot_descriptor(), _resolve_output_path(), _single_or_joined() (+5 more)

### Community 28 - "Community 28"
Cohesion: 0.30
Nodes (13): Exception, _available_fields(), _canonical_fluids(), _config_saturation_coordinate(), _merged_filters(), normalize_visualization(), normalize_visualization_for_source(), _source_available_fields() (+5 more)

### Community 29 - "Community 29"
Cohesion: 0.29
Nodes (12): test_batch_plot_accepts_visualization_only_and_full_configs(), test_batch_plot_rejects_manual_options_files_and_existing_destination(), test_batch_plot_supports_series_and_display_units(), test_inspect_and_batch_execution_do_not_import_coolprop(), test_inspect_conditionally_excludes_unavailable_diagrams(), test_inspect_json_reports_identity_ranges_failures_and_display_units(), test_inspect_reports_available_plot_contracts(), test_inspect_reports_invalid_rows() (+4 more)

### Community 30 - "Community 30"
Cohesion: 0.33
Nodes (10): CompletedProcess, add_configured_visualization(), add_sweep_comparison_plots(), build_generate_arguments(), build_plot_arguments(), build_prepare_arguments(), build_sweep_arguments(), enable_preparation_array_exports() (+2 more)

### Community 31 - "Community 31"
Cohesion: 0.22
Nodes (9): test_dynamic_range_advisory_never_changes_scale(), test_every_registered_unit_has_a_display_mapping(), test_field_registry_covers_properties_and_scientific_units(), test_generation_without_visualization_does_not_import_matplotlib(), test_grouping_rejects_null_group_labels(), test_grouping_requires_explicit_resolution_when_ambiguous(), test_plot_request_rejects_invalid_field_contracts(), format_unit() (+1 more)

### Community 32 - "Community 32"
Cohesion: 0.25
Nodes (6): canonical_display_unit(), DisplayUnitDefinition, from_si(), supported_display_units(), to_si(), validate_display_unit()

### Community 33 - "Community 33"
Cohesion: 0.38
Nodes (8): RunResult, SweepResult, ComparisonArtifacts, _deltas_frame(), _finite_float(), _read_child_dataset(), _values_frame(), write_comparison_artifacts()

### Community 35 - "Community 35"
Cohesion: 0.42
Nodes (8): test_configured_plot_failure_preserves_run_and_successes(), test_configured_visualization_writes_report_and_shared_request_id(), test_dataset_and_configured_figure_directories_cannot_collide(), test_visualization_dependency_failure_prevents_run_creation(), test_visualization_is_excluded_from_dataset_identity(), test_visualization_request_normalization_and_static_validation(), test_zero_valid_rows_skip_configured_visualization(), _write_property_config()

### Community 36 - "Community 36"
Cohesion: 0.62
Nodes (6): _generate_parquet(), _reset_reference_state(), test_normal_boiling_point_is_within_nist_interval(), test_property_table_matches_direct_coolprop(), test_saturation_table_matches_direct_coolprop(), test_vapor_mass_fraction_table_matches_coolprop_and_mixture_invariants()

### Community 37 - "Community 37"
Cohesion: 0.47
Nodes (3): supported_properties(), unsupported_properties(), CoolPropModel

### Community 38 - "Community 38"
Cohesion: 0.33
Nodes (6): Locked uv Development Workflow, Carnopy Quality Checks, Distribution Verification, Python Test Matrix, Quality Job, Verify Workflow

### Community 39 - "Community 39"
Cohesion: 0.53
Nodes (5): build_report(), _counts(), determine_run_status(), _json_number(), RunStatus

### Community 40 - "Community 40"
Cohesion: 0.60
Nodes (5): test_ci_matrix_covers_supported_python_versions(), test_publish_smoke_install_uses_only_production_pypi(), test_publish_workflow_builds_once_and_scopes_oidc_to_publish_jobs(), test_third_party_actions_are_pinned_to_full_commit_shas(), workflow_text()

### Community 41 - "Community 41"
Cohesion: 0.40
Nodes (5): Latest Alpha Security Support, Private Vulnerability Report, Security Policy, Issue Template Config, Private Security Contact Link

### Community 42 - "Community 42"
Cohesion: 0.50
Nodes (4): Release Safeguards, Publish Verified Distributions Workflow, Tag and Source Version Gate, Trusted PyPI Publishing

### Community 43 - "Community 43"
Cohesion: 0.50
Nodes (4): Backend-Derived Synthetic Data, Carnopy Overview, Documented Workflow, Installation Extras

### Community 44 - "Community 44"
Cohesion: 0.83
Nodes (3): main(), sha256_file(), write_checksums()

### Community 45 - "Community 45"
Cohesion: 0.67
Nodes (3): Carnopy Contributor and Coding-Agent Guide, Carnopy Project Identity, Local Instructions Authority

### Community 46 - "Community 46"
Cohesion: 0.67
Nodes (3): Contributor Covenant Code of Conduct, Community Impact Enforcement Guidelines, Harassment-Free Community

## Knowledge Gaps
- **37 isolated node(s):** `carnopy`, `local_gate.sh script`, `Community Impact Enforcement Guidelines`, `Contributing to Carnopy`, `Locked uv Development Workflow` (+32 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CoolPropBackend` connect `Community 20` to `Community 2`, `Community 5`, `Community 37`, `Community 21`, `Community 22`, `Community 23`, `Community 24`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Why does `ConfigError` connect `Community 0` to `Community 1`, `Community 5`, `Community 6`, `Community 8`, `Community 13`, `Community 15`, `Community 21`, `Community 24`, `Community 28`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Why does `PlotRequest` connect `Community 10` to `Community 6`, `Community 7`, `Community 14`, `Community 15`, `Community 16`, `Community 25`, `Community 27`, `Community 28`, `Community 31`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `generate_dataset()` (e.g. with `run_generation()` and `load_config_file()`) actually correct?**
  _`generate_dataset()` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 64 inferred relationships involving `ConfigError` (e.g. with `ConfigModeCli` and `CoolPropModelCli`) actually correct?**
  _`ConfigError` has 64 INFERRED edges - model-reasoned connections that need verification._
- **What connects `carnopy`, `Repository verification tools; not part of the Carnopy wheel.`, `local_gate.sh script` to the rest of the system?**
  _66 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06839945280437756 - nodes in this community are weakly interconnected._