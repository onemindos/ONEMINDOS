// SPDX-License-Identifier: Apache-2.0
// Lists one folder. The spike has no change feed: Finder re-lists a folder when it is opened, and
// enumerateChanges reports nothing new (the real sync client, #707+, uses the sync index revision).
import FileProvider

final class FolderEnumerator: NSObject, NSFileProviderEnumerator {
    private let client: GatewayClient?   // nil = the working set, which this read-only spike keeps empty
    private let path: String
    private static let anchor = NSFileProviderSyncAnchor(Data("spike-0".utf8))

    init(client: GatewayClient?, path: String) {
        self.client = client
        self.path = path
    }

    func invalidate() {}

    func enumerateItems(for observer: NSFileProviderEnumerationObserver, startingAt page: NSFileProviderPage) {
        guard let client else { return observer.finishEnumerating(upTo: nil) }
        Task {
            do {
                let entries = try await client.list(path: path)  // the client already walks every page
                observer.didEnumerate(entries.filter(\.isListable).map(FileProviderItem.init(entry:)))
                observer.finishEnumerating(upTo: nil)
            } catch {
                observer.finishEnumeratingWithError(ProviderErrors.map(error))
            }
        }
    }

    func enumerateChanges(for observer: NSFileProviderChangeObserver, from anchor: NSFileProviderSyncAnchor) {
        observer.finishEnumeratingChanges(upTo: Self.anchor, moreComing: false)
    }

    func currentSyncAnchor(completionHandler: @escaping (NSFileProviderSyncAnchor?) -> Void) {
        completionHandler(Self.anchor)
    }
}
