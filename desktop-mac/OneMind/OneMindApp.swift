// SPDX-License-Identifier: Apache-2.0
// The host app: one window to type the gateway address and a dev token, then add or remove the
// OneMind location in Finder. The File Provider extension ships inside this app.
import SwiftUI

@main
struct OneMindApp: App {
    var body: some Scene {
        WindowGroup("OneMind") { ContentView().frame(minWidth: 440, minHeight: 260) }
            .windowResizability(.contentSize)
    }
}

struct ContentView: View {
    @State private var url = "https://"
    @State private var root = "shared"
    @State private var token = ""
    @State private var status = ""
    @State private var busy = false
    private let store = AppGroupConfigStore()

    var body: some View {
        Form {
            TextField("Gateway address", text: $url)
            TextField("Folder root (shared or home:<id>)", text: $root)
            SecureField("Dev token", text: $token)
            HStack {
                Button("Add OneMind to Finder") { run { try await DomainRegistrar.live.register(url: url, token: token, root: root, store: $0) } }
                    .disabled(busy || token.trimmingCharacters(in: .whitespaces).isEmpty)
                Button("Remove from Finder") { run { try await DomainRegistrar.live.unregister(store: $0) } }
                    .disabled(busy)
            }
            Text(status).foregroundStyle(.secondary).textSelection(.enabled)
            Text("Read-only: files open from OneMind, nothing is written back.").font(.footnote).foregroundStyle(.secondary)
        }
        .padding()
        .onAppear {
            if let c = try? store?.load() { url = c.baseURL.absoluteString; root = c.root; status = "Saved; token present." }
        }
    }

    private func run(_ op: @escaping (ConfigStore) async throws -> Void) {
        guard let store else { status = "App group missing from Info.plist (OneMindAppGroup)."; return }
        busy = true
        Task {
            do { try await op(store); status = "Done." } catch { status = Self.describe(error) }
            token = ""
            busy = false
        }
    }

    private static func describe(_ error: Error) -> String {
        switch error {
        case ConfigError.missingToken: return "A dev token is needed."
        case ConfigError.insecureURL: return "Use https:// (plain http only for this Mac itself)."
        case ConfigError.badURL: return "That address is not valid."
        case ConfigError.badRoot: return "Root must be shared or home:<id>."
        default: return error.localizedDescription
        }
    }
}
