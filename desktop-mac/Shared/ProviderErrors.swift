// SPDX-License-Identifier: Apache-2.0
// The errors Finder understands. A missing token or a 401 is "not signed in" (Finder shows the
// "Sign in" state), a 404 is "no such item", a network failure is "server unreachable".
import FileProvider

public enum ProviderErrors {
    public static func map(_ error: Error) -> Error {
        switch error {
        case ConfigError.missingToken, GatewayError.status(401), GatewayError.status(403):
            return NSFileProviderError(.notAuthenticated)
        case GatewayError.status(404):
            return NSFileProviderError(.noSuchItem)
        case is URLError:
            return NSFileProviderError(.serverUnreachable)
        default:
            return error
        }
    }

    /// Writes from Finder (create, modify, delete, rename, move) are refused in this read-only spike.
    public static func readOnly() -> Error {
        NSError(domain: NSCocoaErrorDomain, code: NSFeatureUnsupportedError,
                userInfo: [NSLocalizedDescriptionKey: "The OneMind location in Finder is read-only."])
    }
}
