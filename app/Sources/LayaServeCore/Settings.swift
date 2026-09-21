import Foundation

/// The settings file that the Python server and this application share.
///
/// The server reads the same file, so every key name must match `laya_serve/config.py`.
public struct Settings: Codable, Equatable, Sendable {
    public var host: String
    public var port: Int
    public var apiKey: String?
    public var defaultModel: String
    public var idleUnloadSeconds: Int
    public var device: String
    public var multiLabelThreshold: Double
    public var fallbackProbabilityFloor: Double
    public var hfToken: String?

    enum CodingKeys: String, CodingKey {
        case host
        case port
        case apiKey = "api_key"
        case defaultModel = "default_model"
        case idleUnloadSeconds = "idle_unload_seconds"
        case device
        case multiLabelThreshold = "multi_label_threshold"
        case fallbackProbabilityFloor = "fallback_probability_floor"
        case hfToken = "hf_token"
    }

    public init(
        host: String = "127.0.0.1",
        port: Int = 5292,
        apiKey: String? = nil,
        defaultModel: String = Models.default,
        idleUnloadSeconds: Int = 900,
        device: String = "auto",
        multiLabelThreshold: Double = 0.5,
        fallbackProbabilityFloor: Double = 0.35,
        hfToken: String? = nil
    ) {
        self.host = host
        self.port = port
        self.apiKey = apiKey
        self.defaultModel = defaultModel
        self.idleUnloadSeconds = idleUnloadSeconds
        self.device = device
        self.multiLabelThreshold = multiLabelThreshold
        self.fallbackProbabilityFloor = fallbackProbabilityFloor
        self.hfToken = hfToken
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let fallback = Settings()
        host = try container.decodeIfPresent(String.self, forKey: .host) ?? fallback.host
        port = try container.decodeIfPresent(Int.self, forKey: .port) ?? fallback.port
        apiKey = try container.decodeIfPresent(String.self, forKey: .apiKey)
        defaultModel =
            try container.decodeIfPresent(String.self, forKey: .defaultModel) ?? fallback.defaultModel
        idleUnloadSeconds =
            try container.decodeIfPresent(Int.self, forKey: .idleUnloadSeconds)
            ?? fallback.idleUnloadSeconds
        device = try container.decodeIfPresent(String.self, forKey: .device) ?? fallback.device
        multiLabelThreshold =
            try container.decodeIfPresent(Double.self, forKey: .multiLabelThreshold)
            ?? fallback.multiLabelThreshold
        fallbackProbabilityFloor =
            try container.decodeIfPresent(Double.self, forKey: .fallbackProbabilityFloor)
            ?? fallback.fallbackProbabilityFloor
        hfToken = try container.decodeIfPresent(String.self, forKey: .hfToken)
    }

    /// The base URL that the user puts into the n8n credential.
    ///
    /// A bind to every interface shows the Bonjour name of the Mac, because `0.0.0.0` is
    /// not an address that another machine can reach.
    public var baseURL: String {
        return "http://\(Settings.displayHost(for: host)):\(port)/v1"
    }

    static func displayHost(for host: String) -> String {
        guard host == "0.0.0.0" || host == "::" else { return host }
        let name = ProcessInfo.processInfo.hostName
        return name.isEmpty ? "127.0.0.1" : name
    }

    public var localBaseURL: URL {
        URL(string: "http://127.0.0.1:\(port)")!
    }

    public var listensOnNetwork: Bool { host != "127.0.0.1" && host != "localhost" }
}

public enum Models {
    public static let all = ["laya", "laya-multilingual", "laya-typed-decisions", "laya-router"]
    public static let `default` = "laya-typed-decisions"

    public static func title(for id: String) -> String {
        switch id {
        case "laya": return "English (421M)"
        case "laya-multilingual": return "Multilingual (322M)"
        case "laya-typed-decisions": return "Typed decisions (421M)"
        case "laya-router": return "Automatic router"
        default: return id
        }
    }
}

/// The choices in the "Unload when idle for" menu.
public enum IdleInterval: CaseIterable, Sendable {
    case never
    case fiveMinutes
    case fifteenMinutes
    case thirtyMinutes
    case oneHour
    case twoHours
    case fourHours

    public var seconds: Int {
        switch self {
        case .never: return 0
        case .fiveMinutes: return 300
        case .fifteenMinutes: return 900
        case .thirtyMinutes: return 1800
        case .oneHour: return 3600
        case .twoHours: return 7200
        case .fourHours: return 14400
        }
    }

    public var title: String {
        switch self {
        case .never: return "Never"
        case .fiveMinutes: return "5 minutes"
        case .fifteenMinutes: return "15 minutes"
        case .thirtyMinutes: return "30 minutes"
        case .oneHour: return "1 hour"
        case .twoHours: return "2 hours"
        case .fourHours: return "4 hours"
        }
    }

    /// The closest choice to a number of seconds that the file holds.
    public static func closest(to seconds: Int) -> IdleInterval {
        if seconds <= 0 { return .never }
        return allCases
            .filter { $0 != .never }
            .min { abs($0.seconds - seconds) < abs($1.seconds - seconds) } ?? .fifteenMinutes
    }
}

/// Read and write the settings file.
public struct SettingsStore {
    public let directory: URL

    public init(directory: URL? = nil) {
        if let directory {
            self.directory = directory
        } else if let override = ProcessInfo.processInfo.environment["LAYA_SERVE_HOME"] {
            self.directory = URL(fileURLWithPath: (override as NSString).expandingTildeInPath)
        } else {
            self.directory = FileManager.default
                .homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/LayaServe", isDirectory: true)
        }
    }

    public var fileURL: URL { directory.appendingPathComponent("config.json") }

    public func load() -> Settings {
        guard let data = try? Data(contentsOf: fileURL),
            let settings = try? JSONDecoder().decode(Settings.self, from: data)
        else {
            return Settings()
        }
        return settings
    }

    public func save(_ settings: Settings) throws {
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(settings).write(to: fileURL, options: .atomic)
    }
}

public func generateAPIKey() -> String {
    var bytes = [UInt8](repeating: 0, count: 18)
    _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
    let encoded = Data(bytes).base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
    return "laya-" + encoded
}
