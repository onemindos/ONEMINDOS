// SPDX-License-Identifier: Apache-2.0
// The extension's gateway calls: GET /v1/files/list (paged by Link rel=next) and GET /v1/files/download
// with Range, as core/onemind_core/routers/files.py serves them.
import XCTest

final class GatewayClientTests: XCTestCase {
    private func client(_ t: FakeTransport) throws -> GatewayClient {
        GatewayClient(config: try GatewayConfig.make(url: "https://box.example", token: " dev-token ", root: "shared"),
                      transport: t)
    }

    func testListSendsTheTokenAndFollowsTheNextLinkOnTheSameHost() async throws {
        let t = FakeTransport([
            (200, ["Link": "</v1/files/list?root=shared&path=%2FDocs&cursor=bzo1MDA&limit=500>; rel=\"next\""],
             json([entry("a.txt", in: "/Docs")])),
            (200, [:], json([entry("Sub", in: "/Docs", type: "dir")])),
        ])
        let items = try await client(t).list(path: "/Docs")
        XCTAssertEqual(items.map(\.name), ["a.txt", "Sub"])
        XCTAssertEqual(items[1].isFolder, true)
        XCTAssertNil(items[1].size)
        let first = try XCTUnwrap(t.requests.first?.url)
        XCTAssertEqual(first.path, "/v1/files/list")
        let q = URLComponents(url: first, resolvingAgainstBaseURL: false)!.queryItems!
        XCTAssertEqual(q.first { $0.name == "root" }?.value, "shared")
        XCTAssertEqual(q.first { $0.name == "path" }?.value, "/Docs")
        XCTAssertEqual(t.requests[0].value(forHTTPHeaderField: "Authorization"), "Bearer dev-token")
        XCTAssertEqual(t.requests[1].url?.host, "box.example")
        XCTAssertEqual(t.requests[1].httpMethod, "GET")
    }

    func testListRefusesANextLinkToAnotherHost() async throws {
        let t = FakeTransport([(200, ["Link": "<https://evil.example/v1/files/list?cursor=x>; rel=\"next\""], json([]))])
        do {
            _ = try await client(t).list(path: "/")
            XCTFail("followed a Link to another host")
        } catch GatewayError.foreignLink {}
        XCTAssertEqual(t.requests.count, 1, "the token must never be sent to another host")
    }

    func testListMapsGatewayStatuses() async throws {
        let t = FakeTransport([(401, [:], json(["error": "unauthenticated"]))])
        do {
            _ = try await client(t).list(path: "/")
            XCTFail("401 accepted")
        } catch GatewayError.status(let code) { XCTAssertEqual(code, 401) }
    }

    func testDownloadUsesRangeChunksWithIfRangeAndReportsProgress() async throws {
        let body = Data("0123456789".utf8)
        let t = FakeTransport([
            (206, ["Content-Range": "bytes 0-3/10", "ETag": "\"a-1\""], body[0..<4]),
            (206, ["Content-Range": "bytes 4-7/10", "ETag": "\"a-1\""], body[4..<8]),
            (206, ["Content-Range": "bytes 8-9/10", "ETag": "\"a-1\""], body[8..<10]),
        ])
        let dest = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dest) }
        let progress = Progress(totalUnitCount: 0)
        let size = try await client(t).download(path: "/Docs/a.txt", to: dest, chunk: 4, progress: progress)
        XCTAssertEqual(size, 10)
        XCTAssertEqual(try Data(contentsOf: dest), body)
        XCTAssertEqual(progress.totalUnitCount, 10)
        XCTAssertEqual(progress.completedUnitCount, 10)
        XCTAssertEqual(t.requests.map { $0.value(forHTTPHeaderField: "Range") }, ["bytes=0-3", "bytes=4-7", "bytes=8-11"])
        XCTAssertNil(t.requests[0].value(forHTTPHeaderField: "If-Range"))
        XCTAssertEqual(t.requests[1].value(forHTTPHeaderField: "If-Range"), "\"a-1\"")
        XCTAssertEqual(t.requests[0].url?.path, "/v1/files/download")
    }

    func testDownloadStartsOverWhenTheFileChangedMidway() async throws {
        let t = FakeTransport([
            (206, ["Content-Range": "bytes 0-3/10", "ETag": "\"a-1\""], Data("0123".utf8)),
            (200, ["ETag": "\"a-2\""], Data("NEW".utf8)),  // If-Range no longer matched: the whole new file
        ])
        let dest = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dest) }
        let size = try await client(t).download(path: "/a.txt", to: dest, chunk: 4, progress: nil)
        XCTAssertEqual(size, 3)
        XCTAssertEqual(try Data(contentsOf: dest), Data("NEW".utf8))
    }

    func testDownloadOfAnEmptyFile() async throws {
        let t = FakeTransport([(416, ["Content-Range": "bytes */0"], json(["error": "conflict"]))])
        let dest = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dest) }
        let size = try await client(t).download(path: "/empty", to: dest, chunk: 4, progress: nil)
        XCTAssertEqual(size, 0)
        XCTAssertEqual(try Data(contentsOf: dest).count, 0)
    }

    func testDownloadRefusesAContentRangeThatDoesNotStartWhereAsked() async throws {
        let t = FakeTransport([(206, ["Content-Range": "bytes 4-7/10"], Data("4567".utf8))])
        let dest = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dest) }
        do {
            _ = try await client(t).download(path: "/a", to: dest, chunk: 4, progress: nil)
            XCTFail("accepted bytes from the wrong offset")
        } catch GatewayError.badRange {}
    }
}
