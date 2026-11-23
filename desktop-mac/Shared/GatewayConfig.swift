// SPDX-License-Identifier: Apache-2.0
// What the host app saves and the extension needs: the gateway address, a typed dev token, and one root.
import Foundation

public enum ConfigError: Error, Equatable {
    case missingToken   // refuse to start without a token (issue #705 "Must refuse")
    case badURL
    case insecureURL    // a bearer token never travels over plain HTTP, except to this Mac itself
    case badRoot
}

public struct GatewayConfig: Equatable {
    public let baseURL: URL
    public let token: String
    public let root: String

    /// Same pattern the gateway enforces on `root` (core/onemind_core/routers/files.py, RootQ).
    static let rootPattern = #"^(?:shared|home:[ -~]{1,200})$"#

    public static func make(url: String, token: String, root: String) throws -> GatewayConfig {
        let token = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !token.isEmpty else { throw ConfigError.missingToken }
        guard let u = URL(string: url.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = u.scheme?.lowercased(), let host = u.host, !host.isEmpty else { throw ConfigError.badURL }
        let loopback = ["127.0.0.1", "::1", "localhost"].contains(host.lowercased())
        guard scheme == "https" || (scheme == "http" && loopback) else {
            throw scheme == "http" ? ConfigError.insecureURL : ConfigError.badURL
        }
        guard root.range(of: rootPattern, options: .regularExpression) != nil else { throw ConfigError.badRoot }
        return GatewayConfig(baseURL: u, token: token, root: root)
    }
}

/// Where the config lives between the app and the extension (ConfigStore.swift has the app-group one).
public protocol ConfigStore {
    /// Throws ConfigError.missingToken when nothing (or no token) is saved.
    func load() throws -> GatewayConfig
    func save(_ config: GatewayConfig) throws
    func clear() throws
}
