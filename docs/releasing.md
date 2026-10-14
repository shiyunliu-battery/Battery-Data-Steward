# Package migration and publishing

Battery Data Steward uses the distribution name `battery-data-steward` from the
planned 0.4.0 release onward. Changing repository files does not create a PyPI
project, transfer the old PyPI project, or rename the GitHub repository.

## Compatibility

- The command remains `bds`; the recommended Python import remains `import bds`.
- `import battery_data_standard`, its submodules, existing exception classes,
  schema versions, target IDs, and serialized export identifiers remain valid.
- `battery-data-steward` and the historical `battery-data-standard` distribution
  install overlapping modules and a shared command. Uninstall the old
  distribution before installing the new one in an existing environment:

  ```bash
  python -m pip uninstall battery-data-standard
  python -m pip install --upgrade battery-data-steward
  ```

- Use the new distribution name for requirements, lockfiles, optional extras,
  and distribution-metadata lookups. Existing old-name pins do not automatically
  migrate. Historical releases and copyright notices retain their original name.

Before publication, install from the reviewed checkout with
`python -m pip install .`. Do not treat the installation command above as proof
that the renamed project already exists on PyPI.

## GitHub repository settings

The repository has been renamed to `Battery-Data-Steward`. Package metadata now
uses its canonical URL:
`https://github.com/shiyunliu-battery/Battery-Data-Steward`.

Set the repository description to:

> Evidence-aware battery data inspection, quality assurance, and preprocessing.

Repository settings require administration access and cannot be changed by a
pull request. The publisher repository name must match the repository running
the release workflow.

## PyPI Trusted Publisher

Configure a publisher for the **new** PyPI project. The old project's publisher
does not authorize publishing a distribution with a different name.

| Setting | Value |
| --- | --- |
| PyPI project name | `battery-data-steward` |
| GitHub owner | `shiyunliu-battery` |
| Repository | `Battery-Data-Steward` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

If the project does not exist, add a pending publisher through
[PyPI account publishing](https://pypi.org/manage/account/publishing/).
If it exists and is owned by this maintainer, add a publisher in its project
settings. A pending publisher does not reserve the name; do not assume name
availability or ownership until publication succeeds. See the
[official pending-publisher instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

## Publish from GitHub Actions

1. Add the new-project Trusted Publisher above in PyPI. Create the GitHub Actions
   environment `pypi` if it is absent.
2. In repository Settings > Secrets and variables > Actions > Variables, add
   `PYPI_TRUSTED_PUBLISHING` with the value `true`.
3. Merge the release-preparation PR. PR #11 and the branding PR are already
   merged; main CI passed before this preparation.
4. Open Actions > Release > Run workflow, choose `main`, and enable **Publish to
   PyPI and create a GitHub Release**. Leave it disabled for a build-only run.
5. The workflow runs tests, lint, formatting, and type checks, verifies the
   package/tag version, builds the distributions, and installs the wheel in a
   clean environment. It then publishes using OIDC and creates `v0.4.0` and a
   GitHub Release with the built artifacts and changelog notes. The version is
   read from the package rather than entered separately.
6. Confirm the workflow's publish and GitHub release jobs succeeded, verify the
   new PyPI project and installation, and then remove the README's
   pre-publication note and add live PyPI links.

Manual publishing is allowed only from `main`. Existing version tags can also
trigger the workflow; a tag must match the package version. A requested release
fails explicitly if the publishing variable is missing rather than silently
skipping the upload. A conflicting existing tag is rejected before publication.

The workflow filename remains **release.yml** and the publishing environment
remains **pypi**. These must match the PyPI publisher. The GitHub Release is
created only after PyPI publication succeeds; a successful build alone does not
mean the package was released. If GitHub Release creation fails after upload,
rerun the failed job rather than republishing the distribution.

Do not delete the historical PyPI project or publish duplicate full packages
under both distribution names. A compatibility-only migration release for the
old project, if desired later, needs a separate reviewed packaging plan.
