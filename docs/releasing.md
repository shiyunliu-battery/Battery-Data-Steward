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

The intended repository name is `battery-data-steward`. Rename the existing
repository in Settings rather than creating an unrelated repository. Code and
metadata currently link to the live `battery-data-standard` repository so they
remain usable before the rename. After the rename, update the repository URLs in
`pyproject.toml`, git remotes, and external references to the new canonical URL.

Set the repository description to:

> Evidence-aware battery data inspection, quality assurance, and preprocessing.

Repository settings require administration access and cannot be changed by a
pull request. Complete the rename before configuring the final publisher so
its repository name matches the repository running the release workflow.

## PyPI Trusted Publisher

Configure a publisher for the **new** PyPI project. The old project's publisher
does not authorize publishing a distribution with a different name.

| Setting | Value |
| --- | --- |
| PyPI project name | `battery-data-steward` |
| GitHub owner | `shiyunliu-battery` |
| Repository | `battery-data-steward` after rename; otherwise `battery-data-standard` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

If the project does not exist, add a pending publisher through
[PyPI account publishing](https://pypi.org/manage/account/publishing/).
If it exists and is owned by this maintainer, add a publisher in its project
settings. A pending publisher does not reserve the name; do not assume name
availability or ownership until publication succeeds. See the
[official pending-publisher instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

The workflow remains `.github/workflows/release.yml`. It builds and checks the
renamed distributions, installs the wheel in a fresh environment, and verifies
both Python imports, package metadata, and the `bds` CLI. Publishing is enabled
only for version tags when the repository variable `PYPI_TRUSTED_PUBLISHING` is
`true`, using the `pypi` environment and OIDC. Update the publisher if the
repository is renamed after setup.

## Release order

1. Merge the scientific-integrity fixes in PR #11 and this branding PR. Resolve
   any shared documentation edits and rerun CI on the combined result.
2. Complete repository settings and new-project Trusted Publisher setup.
3. Confirm the package version is 0.4.0 and move the relevant changelog entries
   into a dated release section.
4. Run tests, lint, format and type checks, build wheel/sdist, and run
   `python -m twine check dist/*`. Install the new wheel in a clean environment.
5. Enable `PYPI_TRUSTED_PUBLISHING`, then create the `v0.4.0` tag on the verified
   commit. This triggers publication; a manual workflow run only builds.
6. Verify the new PyPI project and installation with its extras. Then replace
   the README's pre-publication note and metadata badge with live PyPI links.

Do not delete the historical PyPI project or publish duplicate full packages
under both distribution names. A compatibility-only migration release for the
old project, if desired later, needs a separate reviewed packaging plan.
