# Release Process

This folder holds release-specific **scripts and documents** (tracked
in git) and is the destination for packaged release **artifacts**
(binaries, not tracked — see `.gitignore`). See
[docs/adr/0006-build-system-and-qnx-portability.md](../docs/adr/0006-build-system-and-qnx-portability.md).

## Cutting a release

1. Update `../version.txt` with the new version (bare `MAJOR.MINOR.PATCH`,
   e.g. `0.2.0` — no `v` prefix).
2. Build for each target you're releasing (see the root `README.md`
   for the Linux and QNX SDP 8.0 CMake invocations).
3. Package each build:

   ```sh
   ./scripts/package.sh /path/to/build [platform-tag]
   ```

   `platform-tag` defaults to `<uname -s>-<uname -m>` (e.g.
   `linux-x86_64`); pass something like `qnx-aarch64le` explicitly for
   a QNX cross-build, since `uname` on the build host won't reflect the
   target.

   This produces `release/dist/libReflection-<version>-<platform-tag>.tar.gz`
   containing `lib/libReflection.a`, `include/*.hpp`, and `version.txt`.
4. Publish/distribute the resulting tarball(s) however this project's
   release channel works; `release/dist/` itself is a local, gitignored
   staging area, not a distribution point.

## Bundling the source tree

`release/scripts/create-release-source-bundle.sh` is unrelated to the
build/package steps above — it snapshots the *source*, not a build,
for whenever that's what's needed instead (e.g. handing someone a
clean copy without a `git clone`):

```sh
./scripts/create-release-source-bundle.sh
```

Produces `release/artifacts/libReflection-<version>.zip` (version from
`../version.txt`) containing every file `.gitignore` doesn't exclude —
asks `git ls-files` for that list rather than reimplementing gitignore
pattern matching, so it can never silently disagree with `git status`.
Like `release/dist/`, `release/artifacts/` is a local, gitignored
staging area.
