// SPDX-License-Identifier: Apache-2.0
// What Finder is told about each gateway entry. Identifiers are the gateway path ("/Docs/a.txt");
// "/" is the root container. Capabilities never include writing: the location is read-only.
import FileProvider
import UniformTypeIdentifiers

public enum ItemID {
    public static func identifier(for path: String) -> NSFileProviderItemIdentifier {
        path == "/" || path.isEmpty ? .rootContainer : NSFileProviderItemIdentifier(path)
    }

    public static func path(for id: NSFileProviderItemIdentifier) -> String {
        id == .rootContainer ? "/" : id.rawValue
    }

    public static func parent(of path: String) -> NSFileProviderItemIdentifier {
        var parts = path.split(separator: "/")
        _ = parts.popLast()
        return identifier(for: "/" + parts.joined(separator: "/"))
    }
}

public final class FileProviderItem: NSObject, NSFileProviderItem {
    private let entry: FileEntry?

    public init(entry: FileEntry) { self.entry = entry }
    private override init() { entry = nil }

    /// The top of the OneMind location.
    public static let root = FileProviderItem()

    public var itemIdentifier: NSFileProviderItemIdentifier { entry.map { ItemID.identifier(for: $0.path) } ?? .rootContainer }
    public var parentItemIdentifier: NSFileProviderItemIdentifier { entry.map { ItemID.parent(of: $0.path) } ?? .rootContainer }
    public var filename: String { entry?.name ?? "OneMind" }

    public var contentType: UTType {
        guard let e = entry, !e.isFolder else { return .folder }
        return UTType(filenameExtension: (e.name as NSString).pathExtension) ?? .data
    }

    public var capabilities: NSFileProviderItemCapabilities {
        entry?.isFolder == false ? [.allowsReading] : [.allowsReading, .allowsContentEnumerating]
    }

    public var documentSize: NSNumber? { entry?.size.map { NSNumber(value: $0) } }

    public var contentModificationDate: Date? { entry?.mtime.flatMap(Self.parseDate) }

    public var itemVersion: NSFileProviderItemVersion {
        let content = Data("\(entry?.size ?? -1)|\(entry?.mtime ?? "")|\(entry?.revision ?? -1)".utf8)
        return NSFileProviderItemVersion(contentVersion: content, metadataVersion: content + Data(filename.utf8))
    }

    /// The gateway writes "2026-11-20T10:00:00.123456Z" (fractional seconds optional).
    static func parseDate(_ s: String) -> Date? {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: s) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: s)
    }
}
