// SPDX-License-Identifier: Apache-2.0
// The shared-core route: a Rust library built with UniFFI (core-ffi/) links and answers from Swift.
// The File Provider extension links the same library (FileProvider/CoreProbe.swift).
import OneMindCore
import XCTest

final class CoreFFITests: XCTestCase {
    func testTheRustCoreAnswers() {
        XCTAssertEqual(coreVersion(), "0.1.0")
        XCTAssertEqual(normalizePath(raw: "Docs//a/./b/../c.txt"), "/Docs/a/c.txt")
        XCTAssertEqual(normalizePath(raw: "../../etc"), "/etc")
    }
}
