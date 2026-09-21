import Foundation

/// Talk to the local Python server.
public actor StatusClient {
    private var baseURL: URL
    private let session: URLSession

    public init(baseURL: URL, session: URLSession? = nil) {
        self.baseURL = baseURL
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 5
            configuration.waitsForConnectivity = false
            self.session = URLSession(configuration: configuration)
        }
    }

    public func setBaseURL(_ url: URL) {
        baseURL = url
    }

    /// Return the server status, or nil when the server does not answer.
    public func status() async -> ServerStatus? {
        guard let data = try? await get("/status") else { return nil }
        return try? JSONDecoder().decode(ServerStatus.self, from: data)
    }

    public func unloadNow() async {
        _ = try? await post("/admin/unload", body: [:])
    }

    /// Load the model now, so the first classification does not wait for it.
    public func loadNow() async {
        _ = try? await post("/admin/load", body: [:])
    }

    /// Push a settings change to the running server, so it takes effect at once.
    public func pushSettings(_ settings: Settings) async {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(settings),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }
        _ = try? await post("/admin/config", body: object)
    }

    private func get(_ path: String) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "GET"
        let (data, _) = try await session.data(for: request)
        return data
    }

    private func post(_ path: String, body: [String: Any]) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let settings = SettingsStore().load()
        if let key = settings.apiKey, !key.isEmpty {
            request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        }
        let (data, _) = try await session.data(for: request)
        return data
    }
}
