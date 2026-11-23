// SPDX-License-Identifier: Apache-2.0
// The shared-core question of #705: does a Rust library built with UniFFI link into the sandboxed
// File Provider extension and run there? The extension calls it once at start and logs the answer
// (Console.app, subsystem com.onemindos.mac.fileprovider). The bindings come from core-ffi/ at build time.
import OneMindCore
import os

enum CoreProbe {
    private static var done = false

    static func logOnce() {
        guard !done else { return }
        done = true
        FileProviderExtension.log.info("rust core \(coreVersion(), privacy: .public) linked; probe \(normalizePath(raw: "a//b/../c"), privacy: .public)")
    }
}
