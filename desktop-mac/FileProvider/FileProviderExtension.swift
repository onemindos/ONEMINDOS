// SPDX-License-Identifier: Apache-2.0
// The replicated File Provider extension: the system keeps the files on disk, this process answers
// "what is here" (GET /v1/files/list), "what is this" (GET /v1/files/stat) and "give me the bytes"
// (GET /v1/files/download with Range). Every write is refused; nothing runs without a saved token.
import FileProvider
import os

final class FileProviderExtension: NSObject, NSFileProviderReplicatedExtension {
    private let domain: NSFileProviderDomain
    private let store = AppGroupConfigStore()
    static let log = Logger(subsystem: "com.onemindos.mac.fileprovider", category: "extension")

    required init(domain: NSFileProviderDomain) {
        self.domain = domain
        super.init()
        CoreProbe.logOnce()
    }

    func invalidate() {}

    /// Refuse to start without a token: every entry point goes through here.
    private func client() throws -> GatewayClient {
        guard let store else { throw ConfigError.missingToken }
        return GatewayClient(config: try store.load())
    }

    func item(for identifier: NSFileProviderItemIdentifier, request: NSFileProviderRequest,
              completionHandler: @escaping (NSFileProviderItem?, Error?) -> Void) -> Progress {
        let progress = Progress(totalUnitCount: 1)
        let task = Task {
            do {
                let client = try client()
                if identifier == .rootContainer { return completionHandler(FileProviderItem.root, nil) }
                let entry = try await client.stat(path: ItemID.path(for: identifier))
                completionHandler(FileProviderItem(entry: entry), nil)
            } catch {
                completionHandler(nil, ProviderErrors.map(error))
            }
            progress.completedUnitCount = 1
        }
        progress.cancellationHandler = { task.cancel() }
        return progress
    }

    func fetchContents(for identifier: NSFileProviderItemIdentifier, version requestedVersion: NSFileProviderItemVersion?,
                       request: NSFileProviderRequest,
                       completionHandler: @escaping (URL?, NSFileProviderItem?, Error?) -> Void) -> Progress {
        let progress = Progress(totalUnitCount: 0)
        let task = Task {
            do {
                let client = try client()
                let path = ItemID.path(for: identifier)
                let entry = try await client.stat(path: path)
                guard let manager = NSFileProviderManager(for: domain) else { throw NSFileProviderError(.providerNotFound) }
                let tmp = try manager.temporaryDirectoryURL().appendingPathComponent(UUID().uuidString)
                try await client.download(path: path, to: tmp, progress: progress)
                completionHandler(tmp, FileProviderItem(entry: entry), nil)
            } catch {
                Self.log.error("fetch failed: \(String(describing: error), privacy: .public)")
                completionHandler(nil, nil, ProviderErrors.map(error))
            }
        }
        progress.cancellationHandler = { task.cancel() }
        return progress
    }

    // MARK: - writes: refused

    func createItem(basedOn itemTemplate: NSFileProviderItem, fields: NSFileProviderItemFields, contents url: URL?,
                    options: NSFileProviderCreateItemOptions = [], request: NSFileProviderRequest,
                    completionHandler: @escaping (NSFileProviderItem?, NSFileProviderItemFields, Bool, Error?) -> Void) -> Progress {
        completionHandler(nil, [], false, ProviderErrors.readOnly())
        return Progress(totalUnitCount: 0)
    }

    func modifyItem(_ item: NSFileProviderItem, baseVersion version: NSFileProviderItemVersion,
                    changedFields: NSFileProviderItemFields, contents newContents: URL?,
                    options: NSFileProviderModifyItemOptions = [], request: NSFileProviderRequest,
                    completionHandler: @escaping (NSFileProviderItem?, NSFileProviderItemFields, Bool, Error?) -> Void) -> Progress {
        completionHandler(nil, [], false, ProviderErrors.readOnly())
        return Progress(totalUnitCount: 0)
    }

    func deleteItem(identifier: NSFileProviderItemIdentifier, baseVersion version: NSFileProviderItemVersion,
                    options: NSFileProviderDeleteItemOptions = [], request: NSFileProviderRequest,
                    completionHandler: @escaping (Error?) -> Void) -> Progress {
        completionHandler(ProviderErrors.readOnly())
        return Progress(totalUnitCount: 0)
    }

    // MARK: - listing

    func enumerator(for containerItemIdentifier: NSFileProviderItemIdentifier,
                    request: NSFileProviderRequest) throws -> NSFileProviderEnumerator {
        let client: GatewayClient
        do { client = try self.client() } catch { throw ProviderErrors.map(error) }
        if containerItemIdentifier == .workingSet { return FolderEnumerator(client: nil, path: "/") }
        return FolderEnumerator(client: client, path: ItemID.path(for: containerItemIdentifier))
    }
}
