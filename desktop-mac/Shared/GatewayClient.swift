// SPDX-License-Identifier: Apache-2.0
// The two gateway calls the read-only Finder location needs. Read-only by construction: this client has
// no method that sends anything but GET.
import Foundation

public protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionTransport: HTTPTransport {
    private let session: URLSession
    public init() {
        let c = URLSessionConfiguration.ephemeral  // no cookie jar, no disk cache of file bytes
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: c)
    }
    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, resp) = try await session.data(for: request)
        guard let http = resp as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        return (data, http)
    }
}

public enum GatewayError: Error, Equatable {
    case status(Int)
    case foreignLink   // a Link rel=next pointing at another origin: never send the token there
    case badRange      // a 206 whose Content-Range does not start where we asked
    case badBody
}

/// One row of GET /v1/files/list (and GET /v1/files/stat), FilesService._entry in core/.
public struct FileEntry: Decodable, Equatable {
    public let name: String
    public let path: String
    public let type: String
    public let size: Int64?
    public let mtime: String?
    public let mime: String?
    public let revision: Int64?

    public var isFolder: Bool { type == "dir" }
    /// Symlinks and special files are left out of Finder in this spike.
    public var isListable: Bool { type == "dir" || type == "file" }
}

public struct GatewayClient {
    public let config: GatewayConfig
    private let transport: HTTPTransport
    static let pageLimit = 500  // the gateway's maximum (le=500)
    static let maxPages = 200

    public init(config: GatewayConfig, transport: HTTPTransport = URLSessionTransport()) {
        self.config = config
        self.transport = transport
    }

    /// Every entry of one folder, following RFC 8288 Link rel=next on the gateway's own origin only.
    public func list(path: String) async throws -> [FileEntry] {
        var next: URL? = url("/v1/files/list", ["root": config.root, "path": path, "limit": String(Self.pageLimit)])
        var out: [FileEntry] = []
        var pages = 0
        while let u = next, pages < Self.maxPages {
            let (data, resp) = try await get(u)
            guard resp.statusCode == 200 else { throw GatewayError.status(resp.statusCode) }
            guard let rows = try? JSONDecoder().decode([FileEntry].self, from: data) else { throw GatewayError.badBody }
            out += rows
            next = try nextLink(resp.value(forHTTPHeaderField: "Link"))
            pages += 1
        }
        return out
    }

    public func stat(path: String) async throws -> FileEntry {
        let (data, resp) = try await get(url("/v1/files/stat", ["root": config.root, "path": path]))
        guard resp.statusCode == 200 else { throw GatewayError.status(resp.statusCode) }
        guard let e = try? JSONDecoder().decode(FileEntry.self, from: data) else { throw GatewayError.badBody }
        return e
    }

    /// Downloads in Range chunks so a large file shows progress and a change mid-download is noticed
    /// (If-Range with the first ETag: the gateway answers 200 with the whole new file). Returns the size.
    @discardableResult
    public func download(path: String, to dest: URL, chunk: Int64 = 8 << 20, progress: Progress?) async throws -> Int64 {
        FileManager.default.createFile(atPath: dest.path, contents: nil)
        let fh = try FileHandle(forWritingTo: dest)
        defer { try? fh.close() }
        var offset: Int64 = 0
        var etag: String?
        let u = url("/v1/files/download", ["root": config.root, "path": path])
        while true {
            try Task.checkCancellation()
            if progress?.isCancelled == true { throw CancellationError() }
            var extra = ["Range": "bytes=\(offset)-\(offset + chunk - 1)"]
            if let etag { extra["If-Range"] = etag }
            let (data, resp) = try await get(u, headers: extra)
            switch resp.statusCode {
            case 206:
                guard let (start, end, total) = Self.contentRange(resp.value(forHTTPHeaderField: "Content-Range")),
                      start == offset, end - start + 1 == Int64(data.count) else { throw GatewayError.badRange }
                etag = etag ?? resp.value(forHTTPHeaderField: "ETag")
                try fh.seek(toOffset: UInt64(offset))
                try fh.write(contentsOf: data)
                offset = end + 1
                progress?.totalUnitCount = total
                progress?.completedUnitCount = offset
                if offset >= total { return offset }
            case 200:  // no range support, or the file changed since the first chunk: this is the whole file
                try fh.truncate(atOffset: 0)
                try fh.write(contentsOf: data)
                progress?.totalUnitCount = Int64(data.count)
                progress?.completedUnitCount = Int64(data.count)
                return Int64(data.count)
            case 416 where offset == 0 && resp.value(forHTTPHeaderField: "Content-Range") == "bytes */0":
                return 0  // an empty file: no byte range can describe it
            default:
                throw GatewayError.status(resp.statusCode)
            }
        }
    }

    // MARK: - helpers

    private func url(_ path: String, _ query: [String: String]) -> URL {
        var c = URLComponents(url: config.baseURL, resolvingAgainstBaseURL: false)!
        c.path = path
        c.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        return c.url!
    }

    private func get(_ u: URL, headers: [String: String] = [:]) async throws -> (Data, HTTPURLResponse) {
        var r = URLRequest(url: u)
        r.httpMethod = "GET"
        r.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization")
        r.setValue("application/json", forHTTPHeaderField: "Accept")
        for (k, v) in headers { r.setValue(v, forHTTPHeaderField: k) }
        return try await transport.send(r)
    }

    private func nextLink(_ header: String?) throws -> URL? {
        guard let header else { return nil }
        for part in header.split(separator: ",") {
            let bits = part.split(separator: ";").map { $0.trimmingCharacters(in: .whitespaces) }
            guard bits.count >= 2, bits.dropFirst().contains(where: { $0.replacingOccurrences(of: " ", with: "") == "rel=\"next\"" }),
                  bits[0].hasPrefix("<"), bits[0].hasSuffix(">") else { continue }
            let raw = String(bits[0].dropFirst().dropLast())
            guard let u = URL(string: raw, relativeTo: config.baseURL)?.absoluteURL else { throw GatewayError.badBody }
            guard u.scheme == config.baseURL.scheme, u.host == config.baseURL.host, u.port == config.baseURL.port
            else { throw GatewayError.foreignLink }
            return u
        }
        return nil
    }

    /// "bytes 0-3/10" -> (0, 3, 10)
    static func contentRange(_ header: String?) -> (Int64, Int64, Int64)? {
        guard let h = header, h.hasPrefix("bytes ") else { return nil }
        let parts = h.dropFirst(6).split(separator: "/")
        guard parts.count == 2, let total = Int64(parts[1]) else { return nil }
        let se = parts[0].split(separator: "-")
        guard se.count == 2, let s = Int64(se[0]), let e = Int64(se[1]), s <= e, e < total else { return nil }
        return (s, e, total)
    }
}
