# Package migration and publishing

Battery Data Steward uses the distribution name `battery-data-steward`, the
repository `Battery-Data-Steward`, and, from 0.7.0, the canonical Python package
`battery_data_steward`. The PyPI project already exists. Updating source files
prepares a release; it does not publish the package.

## Migrating to 0.7.0

The namespace change is a breaking import change from 0.6.x and earlier:

- Use `import battery_data_steward as bds`, or keep the high-level `import bds`
  alias. Submodule imports now start with `battery_data_steward`, for example
  `from battery_data_steward.export import to_export_frame`.
- The command remains `bds`. Module execution is
  `python -m battery_data_steward` or `python -m battery_data_steward.cli`.
- The public base exception is `BatteryDataStewardError`. Its specialized
  subclasses, such as `ConversionError`, keep their names.
- New export reports use `battery-data-steward-export-v1` as their export-format
  identifier. Export columns, values, units and scientific calculations are
  unchanged by the rename. Consumers that inspect the identifier must accept the
  new value; historical reports retain the identifier written by their producer.
- The canonical BDS export target is `bds`; Steward-named aliases are also
  accepted. Update configurations that use an earlier project-name alias.
- The previous Python namespace is no longer installed. Update downstream
  imports before upgrading their dependency requirement to 0.7.x. Existing
  applications pinned to 0.6.x can keep using that release while they migrate.
- Prefer a fresh virtual environment to avoid stale modules or overlapping
  installations from older distributions. Use `battery-data-steward` for
  requirements, lockfiles, optional extras and distribution-metadata lookups.

Install the matching release with
`python -m pip install "battery-data-steward==0.7.2"` in a fresh environment. The
current documentation and notebooks use the 0.7.0 namespace; an older release
does not provide it. For development, install from the repository root with
`python -m pip install -e ".[dev]"`.

## GitHub repository settings

Package metadata uses the canonical repository URL:
`https://github.com/shiyunliu-battery/Battery-Data-Steward`.

Recommended repository description:

> Evidence-aware battery data inspection, quality assurance, and preprocessing.

The publisher repository name must match the repository running the release
workflow.

## PyPI Trusted Publisher

The existing PyPI project's Trusted Publisher uses these settings:

| Setting | Value |
| --- | --- |
| PyPI project name | `battery-data-steward` |
| GitHub owner | `shiyunliu-battery` |
| Repository | `Battery-Data-Steward` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

Verify the publisher in the project's PyPI publishing settings when changing
repository ownership, workflow filename or environment. A Python namespace
rename does not require a new PyPI project.

## Publish from GitHub Actions

1. Verify the Trusted Publisher above and the GitHub Actions environment `pypi`.
2. Confirm the repository Actions variable `PYPI_TRUSTED_PUBLISHING` is `true`.
3. Prepare the package version, dated changelog section and documentation on
   `main`; wait for CI to pass.
4. Open Actions > Release > Run workflow, choose `main`, and enable **Publish to
   PyPI and create a GitHub Release**. Leave it disabled for a build-only run.
5. The workflow runs tests, lint, formatting and type checks, verifies the
   package/tag version, builds the distributions and installs the wheel in a
   clean environment. It then publishes using OIDC and creates `v<version>` and
   a GitHub Release with the built artifacts and changelog notes. The version is
   read from the package rather than entered separately.
6. Confirm the workflow's publish and GitHub release jobs succeeded. Verify the
   version on PyPI and test the installed wheel in a fresh environment.

Manual publishing is allowed only from `main`. Existing version tags can also
trigger the workflow; a tag must match the package version. A requested release
fails explicitly if the publishing variable is missing rather than silently
skipping the upload. A conflicting existing tag is rejected before publication.

The workflow filename remains **release.yml** and the publishing environment
remains **pypi**. These must match the PyPI publisher. The GitHub Release is
created only after PyPI publication succeeds; a successful build alone does not
mean the package was released. If GitHub Release creation fails after upload,
rerun the failed job rather than republishing the distribution.
