// SPDX-License-Identifier: Apache-2.0
// The host app registers exactly one File Provider domain ("OneMind" under Locations in Finder).
import FileProvider

public struct DomainRegistrar {
    public static let domainID = NSFileProviderDomainIdentifier("onemind")
    public static var domain: NSFileProviderDomain { NSFileProviderDomain(identifier: domainID, displayName: "OneMind") }

    private let add: (NSFileProviderDomain) async throws -> Void
    private let remove: (NSFileProviderDomain) async throws -> Void

    public init(add: @escaping (NSFileProviderDomain) async throws -> Void,
                remove: @escaping (NSFileProviderDomain) async throws -> Void) {
        self.add = add
        self.remove = remove
    }

    /// The real NSFileProviderManager. Removal uses .removeAll so nothing stays in ~/Library/CloudStorage.
    public static let live = DomainRegistrar(
        add: { try await NSFileProviderManager.add($0) },
        remove: { _ = try await NSFileProviderManager.remove($0, mode: .removeAll) })

    /// Validates first: without a token nothing is saved and the manager is never called.
    public func register(url: String, token: String, root: String, store: ConfigStore) async throws {
        let config = try GatewayConfig.make(url: url, token: token, root: root)
        try store.save(config)
        try await add(Self.domain)
    }

    public func unregister(store: ConfigStore) async throws {
        try await remove(Self.domain)
        try store.clear()
    }
}
