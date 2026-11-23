// SPDX-License-Identifier: Apache-2.0
// Must refuse (issue #705): no start without a token, and no writes from Finder.
import FileProvider
import XCTest

final class RefusalTests: XCTestCase {
    func testConfigRefusesAMissingOrBlankToken() {
        for token in ["", "   ", "\n"] {
            XCTAssertThrowsError(try GatewayConfig.make(url: "https://box.example", token: token, root: "shared")) {
                XCTAssertEqual($0 as? ConfigError, .missingToken)
            }
        }
    }

    func testConfigRefusesPlainHTTPExceptLoopbackAndBadRoots() {
        XCTAssertThrowsError(try GatewayConfig.make(url: "http://box.example", token: "t", root: "shared")) {
            XCTAssertEqual($0 as? ConfigError, .insecureURL)
        }
        XCTAssertNoThrow(try GatewayConfig.make(url: "http://127.0.0.1:8080", token: "t", root: "shared"))
        XCTAssertThrowsError(try GatewayConfig.make(url: "not a url", token: "t", root: "shared"))
        XCTAssertThrowsError(try GatewayConfig.make(url: "https://box.example", token: "t", root: "../etc")) {
            XCTAssertEqual($0 as? ConfigError, .badRoot)
        }
        XCTAssertNoThrow(try GatewayConfig.make(url: "https://box.example", token: "t", root: "home:per_1"))
    }

    func testRegisteringTheDomainWithoutATokenNeverReachesTheManager() async {
        var added: [NSFileProviderDomain] = []
        let store = MemoryConfigStore()
        let registrar = DomainRegistrar(add: { added.append($0) }, remove: { _ in })
        do {
            try await registrar.register(url: "https://box.example", token: "", root: "shared", store: store)
            XCTFail("registered without a token")
        } catch { XCTAssertEqual(error as? ConfigError, .missingToken) }
        XCTAssertTrue(added.isEmpty)
        XCTAssertNil(store.saved)
    }

    func testRegisteringAddsOneDomainAndSavesTheConfig() async throws {
        var added: [NSFileProviderDomain] = []
        let store = MemoryConfigStore()
        let registrar = DomainRegistrar(add: { added.append($0) }, remove: { _ in })
        try await registrar.register(url: "https://box.example", token: "tok", root: "shared", store: store)
        XCTAssertEqual(added.map(\.identifier), [DomainRegistrar.domainID])
        XCTAssertEqual(added.first?.displayName, "OneMind")
        XCTAssertEqual(store.saved?.token, "tok")
    }

    func testAMissingTokenAtRuntimeIsNotAuthenticated() {
        let err = ProviderErrors.map(ConfigError.missingToken) as NSError
        XCTAssertEqual(err.domain, NSFileProviderErrorDomain)
        XCTAssertEqual(err.code, NSFileProviderError.notAuthenticated.rawValue)
        XCTAssertEqual((ProviderErrors.map(GatewayError.status(401)) as NSError).code, NSFileProviderError.notAuthenticated.rawValue)
        XCTAssertEqual((ProviderErrors.map(GatewayError.status(404)) as NSError).code, NSFileProviderError.noSuchItem.rawValue)
        XCTAssertEqual((ProviderErrors.map(URLError(.timedOut)) as NSError).code, NSFileProviderError.serverUnreachable.rawValue)
    }

    func testWritesAreRefused() {
        let err = ProviderErrors.readOnly() as NSError
        XCTAssertEqual(err.domain, NSCocoaErrorDomain)
        XCTAssertEqual(err.code, NSFeatureUnsupportedError)
    }

    func testItemsNeverOfferWriteCapabilities() throws {
        let data = json([entry("a.txt"), entry("Docs", type: "dir")])
        let entries = try JSONDecoder().decode([FileEntry].self, from: data)
        let file = FileProviderItem(entry: entries[0]), dir = FileProviderItem(entry: entries[1])
        XCTAssertEqual(file.capabilities, [.allowsReading])
        XCTAssertEqual(dir.capabilities, [.allowsReading, .allowsContentEnumerating])
        XCTAssertEqual(FileProviderItem.root.capabilities, [.allowsReading, .allowsContentEnumerating])
    }
}
