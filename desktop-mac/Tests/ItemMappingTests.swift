// SPDX-License-Identifier: Apache-2.0
// Gateway paths <-> File Provider identifiers, and what Finder is told about each item.
import FileProvider
import UniformTypeIdentifiers
import XCTest

final class ItemMappingTests: XCTestCase {
    func testIdentifiersRoundTripAndTheRootIsTheRootContainer() {
        XCTAssertEqual(ItemID.identifier(for: "/"), .rootContainer)
        XCTAssertEqual(ItemID.path(for: .rootContainer), "/")
        XCTAssertEqual(ItemID.path(for: ItemID.identifier(for: "/Docs/a b.txt")), "/Docs/a b.txt")
        XCTAssertEqual(ItemID.parent(of: "/Docs/a.txt"), ItemID.identifier(for: "/Docs"))
        XCTAssertEqual(ItemID.parent(of: "/a.txt"), .rootContainer)
    }

    func testAFileItemCarriesSizeTypeDateAndAVersion() throws {
        let e = try JSONDecoder().decode(FileEntry.self, from: json(entry("Report.pdf", in: "/Docs", size: 209_715_200)))
        let item = FileProviderItem(entry: e)
        XCTAssertEqual(item.filename, "Report.pdf")
        XCTAssertEqual(item.itemIdentifier.rawValue, "/Docs/Report.pdf")
        XCTAssertEqual(item.parentItemIdentifier.rawValue, "/Docs")
        XCTAssertEqual(item.documentSize?.int64Value, 209_715_200)
        XCTAssertEqual(item.contentType, .pdf)
        XCTAssertNotNil(item.contentModificationDate)
        XCTAssertFalse(item.itemVersion.contentVersion.isEmpty)
    }

    func testAFolderItem() throws {
        let e = try JSONDecoder().decode(FileEntry.self, from: json(entry("Docs", type: "dir")))
        let item = FileProviderItem(entry: e)
        XCTAssertEqual(item.contentType, .folder)
        XCTAssertEqual(item.parentItemIdentifier, .rootContainer)
    }

    func testOnlyFilesAndFoldersAreShown() throws {
        let rows = json([entry("a", type: "file"), entry("l", type: "symlink"), entry("d", type: "dir")])
        let entries = try JSONDecoder().decode([FileEntry].self, from: rows)
        XCTAssertEqual(entries.filter(\.isListable).map(\.name), ["a", "d"])
    }
}
