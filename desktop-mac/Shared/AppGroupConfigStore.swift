// SPDX-License-Identifier: Apache-2.0
// The config both processes read: address and root in the app group's defaults, the token in the
// data-protection keychain under the app group as access group. The group id comes from Info.plist
// (OneMindAppGroup, set from the build setting ONEMIND_APP_GROUP), so its final form is one setting.
import Foundation
import Security

public struct AppGroupConfigStore: ConfigStore {
    public let groupID: String
    private static let service = "com.onemindos.mac.dev-token"

    public init?(bundle: Bundle = .main) {
        guard let g = bundle.object(forInfoDictionaryKey: "OneMindAppGroup") as? String, !g.isEmpty else { return nil }
        groupID = g
    }

    private var defaults: UserDefaults? { UserDefaults(suiteName: groupID) }

    public func load() throws -> GatewayConfig {
        guard let d = defaults, let url = d.string(forKey: "gatewayURL"), let root = d.string(forKey: "root"),
              let token = try readToken() else { throw ConfigError.missingToken }
        return try GatewayConfig.make(url: url, token: token, root: root)
    }

    public func save(_ config: GatewayConfig) throws {
        try writeToken(config.token)
        defaults?.set(config.baseURL.absoluteString, forKey: "gatewayURL")
        defaults?.set(config.root, forKey: "root")
    }

    public func clear() throws {
        defaults?.removeObject(forKey: "gatewayURL")
        defaults?.removeObject(forKey: "root")
        let status = SecItemDelete(baseQuery() as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw keychainError(status) }
    }

    private func baseQuery() -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: Self.service,
         kSecAttrAccessGroup as String: groupID,
         kSecUseDataProtectionKeychain as String: true]
    }

    private func readToken() throws -> String? {
        var q = baseQuery()
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &out)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = out as? Data else { throw keychainError(status) }
        return String(data: data, encoding: .utf8)
    }

    private func writeToken(_ token: String) throws {
        let data = Data(token.utf8)
        let status = SecItemUpdate(baseQuery() as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var add = baseQuery()
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            let s = SecItemAdd(add as CFDictionary, nil)
            guard s == errSecSuccess else { throw keychainError(s) }
        } else if status != errSecSuccess {
            throw keychainError(status)
        }
    }

    private func keychainError(_ status: OSStatus) -> Error {
        NSError(domain: NSOSStatusErrorDomain, code: Int(status))
    }
}
