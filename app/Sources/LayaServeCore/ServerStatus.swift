import Foundation

/// The reply from `GET /status` on the Python server.
public struct ServerStatus: Codable, Equatable, Sendable {
    public var state: String
    public var model: String?
    public var device: String?
    public var idleSeconds: Double?
    public var idleUnloadSeconds: Int?
    public var rssMB: Double?
    public var error: String?
    public var fakeModel: Bool?
    public var exposedWithoutKey: Bool?
    /// The checkpoints that ship inside the application. Any other one needs a download.
    public var bundledModels: [String]?

    enum CodingKeys: String, CodingKey {
        case state
        case model
        case device
        case idleSeconds = "idle_seconds"
        case idleUnloadSeconds = "idle_unload_seconds"
        case rssMB = "rss_mb"
        case error
        case fakeModel = "fake_model"
        case exposedWithoutKey = "exposed_without_key"
        case bundledModels = "bundled_models"
    }

    public init(
        state: String,
        model: String? = nil,
        device: String? = nil,
        idleSeconds: Double? = nil,
        idleUnloadSeconds: Int? = nil,
        rssMB: Double? = nil,
        error: String? = nil,
        fakeModel: Bool? = nil,
        exposedWithoutKey: Bool? = nil,
        bundledModels: [String]? = nil
    ) {
        self.state = state
        self.model = model
        self.device = device
        self.idleSeconds = idleSeconds
        self.idleUnloadSeconds = idleUnloadSeconds
        self.rssMB = rssMB
        self.error = error
        self.fakeModel = fakeModel
        self.exposedWithoutKey = exposedWithoutKey
        self.bundledModels = bundledModels
    }
}

/// What the menu bar shows.
public enum MenuState: Equatable, Sendable {
    case starting
    case unloaded
    case loaded(model: String, device: String, rssMB: Double?)
    case failed(String)

    public var symbolName: String {
        switch self {
        case .starting: return "circle.dotted"
        case .unloaded: return "moon.zzz"
        case .loaded: return "brain"
        case .failed: return "exclamationmark.triangle"
        }
    }

    public var title: String {
        switch self {
        case .starting:
            return "Starting the server..."
        case .unloaded:
            return "Model unloaded. The next request loads it."
        case .loaded(let model, let device, let rssMB):
            let memory = rssMB.map { String(format: " %.0f MB", $0) } ?? ""
            return "Loaded \(model) on \(device)\(memory)"
        case .failed(let message):
            return "Error: \(message)"
        }
    }

    /// Build the menu state from a status reply. A nil status means the server is not up yet.
    public static func from(_ status: ServerStatus?) -> MenuState {
        guard let status else { return .starting }
        switch status.state {
        case "loaded":
            return .loaded(
                model: status.model ?? "unknown",
                device: status.device ?? "unknown",
                rssMB: status.rssMB)
        case "error":
            return .failed(status.error ?? "unknown error")
        default:
            return .unloaded
        }
    }
}
