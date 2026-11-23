// SPDX-License-Identifier: Apache-2.0
// Test-only transport: answers from a script of canned gateway replies and records every request.
// It lives in the test bundle (which compiles Shared/ directly), so no shipped target can reach it.
import Foundation

final class FakeTransport: HTTPTransport, @unchecked Sendable {
    typealias Reply = (status: Int, headers: [String: String], body: Data)
    private let lock = NSLock()
    private var replies: [Reply]
    private(set) var requests: [URLRequest] = []

    init(_ replies: [Reply]) { self.replies = replies }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        try next(request)
    }

    private func next(_ request: URLRequest) throws -> (Data, HTTPURLResponse) {
        lock.lock(); defer { lock.unlock() }
        requests.append(request)
        guard !replies.isEmpty else { throw URLError(.cannotConnectToHost) }
        let r = replies.removeFirst()
        let resp = HTTPURLResponse(url: request.url!, statusCode: r.status, httpVersion: "HTTP/1.1", headerFields: r.headers)!
        return (r.body, resp)
    }
}

final class MemoryConfigStore: ConfigStore {
    var saved: GatewayConfig?
    func load() throws -> GatewayConfig {
        guard let saved else { throw ConfigError.missingToken }
        return saved
    }
    func save(_ config: GatewayConfig) throws { saved = config }
    func clear() throws { saved = nil }
}

func json(_ object: Any) -> Data { try! JSONSerialization.data(withJSONObject: object) }

func entry(_ name: String, in parent: String = "/", type: String = "file", size: Int? = 3) -> [String: Any] {
    let path = parent == "/" ? "/\(name)" : "\(parent)/\(name)"
    var e: [String: Any] = ["name": name, "path": path, "type": type, "mtime": "2026-11-20T10:00:00.123456Z"]
    e["size"] = type == "file" ? size as Any : NSNull()
    if type == "file" { e["mime"] = "text/plain" }
    return e
}
