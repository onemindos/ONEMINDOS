#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Xcode "Run Script" phase (extension and test targets). Builds the shared Rust core and hands it to Swift:
#   1. cargo builds core-ffi/ as a static library for each arch being built (lipo merges them);
#   2. uniffi-bindgen generates the Swift bindings from that library;
#   3. swiftc compiles the bindings into a static Swift module, OneMindCore, that targets `import`.
# Output in $DERIVED_FILE_DIR/core-ffi: libonemind_core_ffi.a, libOneMindCore.a, OneMindCore.swiftmodule/,
# module.modulemap + onemind_core_ffiFFI.h. (Xcode does not compile Swift files a script phase writes,
# hence step 3.) Needs Rust (rustup) with aarch64-apple-darwin, plus x86_64-apple-darwin for universal builds.
set -eu
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
# Xcode exports hundreds of build settings as environment variables; some of them break cargo (a proc-macro
# crate then "cannot be found"). Run cargo with a clean environment and only what it needs.
clean() { env -i HOME="$HOME" PATH="$PATH" MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-14.0}" "$@"; }
command -v cargo >/dev/null || { echo "error: cargo not found; install Rust (rustup) to build the core-ffi library (desktop-mac/README.md)"; exit 1; }
CRATE="$SRCROOT/core-ffi"
OUT="$DERIVED_FILE_DIR/core-ffi"
MIN="${MACOSX_DEPLOYMENT_TARGET:-14.0}"
rm -rf "$OUT" && mkdir -p "$OUT/obj"
rust_libs="" swift_libs=""
for arch in ${ARCHS:-arm64}; do
  case "$arch" in
    arm64) triple=aarch64-apple-darwin ;;
    x86_64) triple=x86_64-apple-darwin ;;
    *) echo "error: unsupported arch $arch"; exit 1 ;;
  esac
  # MACOSX_DEPLOYMENT_TARGET makes the Rust objects match the app's minimum macOS.
  clean cargo build --locked --manifest-path "$CRATE/Cargo.toml" --release --target "$triple" --lib
  rust_libs="$rust_libs $CRATE/target/$triple/release/libonemind_core_ffi.a"
done
# shellcheck disable=SC2086
lipo -create $rust_libs -output "$OUT/libonemind_core_ffi.a"
# Library mode reads the crate config through `cargo metadata`, which looks in the working directory.
first=$(echo "$rust_libs" | awk '{print $1}')
(cd "$CRATE" && clean cargo run --locked --quiet --release --bin uniffi-bindgen -- \
  generate --library "$first" --language swift --out-dir "$OUT/gen")
cp "$OUT/gen/onemind_core_ffiFFI.h" "$OUT/onemind_core_ffiFFI.h"
cp "$OUT/gen/onemind_core_ffiFFI.modulemap" "$OUT/module.modulemap"
for arch in ${ARCHS:-arm64}; do
  mkdir -p "$OUT/obj/$arch" "$OUT/OneMindCore.swiftmodule"
  xcrun --sdk macosx swiftc -parse-as-library -emit-library -static -emit-module -module-name OneMindCore \
    -target "$arch-apple-macos$MIN" -application-extension -O -swift-version 5 -I "$OUT" \
    -module-cache-path "$OUT/mcache" \
    -emit-module-path "$OUT/OneMindCore.swiftmodule/$arch-apple-macos.swiftmodule" \
    -o "$OUT/obj/$arch/libOneMindCore.a" "$OUT/gen/onemind_core_ffi.swift"
  swift_libs="$swift_libs $OUT/obj/$arch/libOneMindCore.a"
done
# shellcheck disable=SC2086
lipo -create $swift_libs -output "$OUT/libOneMindCore.a"
