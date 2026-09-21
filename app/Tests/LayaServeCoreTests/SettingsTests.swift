import XCTest

@testable import LayaServeCore

final class SettingsTests: XCTestCase {
    func testDefaultsMatchThePythonServer() {
        let settings = Settings()
        XCTAssertEqual(settings.host, "127.0.0.1")
        XCTAssertEqual(settings.port, 5292)
        XCTAssertEqual(settings.defaultModel, "laya-typed-decisions")
        XCTAssertEqual(settings.idleUnloadSeconds, 900)
        XCTAssertNil(settings.apiKey)
    }

    func testTheKeysMatchTheConfigFile() throws {
        let json = """
            {
              "host": "0.0.0.0",
              "port": 6000,
              "api_key": "secret",
              "default_model": "laya-multilingual",
              "idle_unload_seconds": 60,
              "device": "cpu",
              "multi_label_threshold": 0.7,
              "fallback_probability_floor": 0.2,
              "hf_token": null
            }
            """
        let settings = try JSONDecoder().decode(Settings.self, from: Data(json.utf8))
        XCTAssertEqual(settings.host, "0.0.0.0")
        XCTAssertEqual(settings.port, 6000)
        XCTAssertEqual(settings.apiKey, "secret")
        XCTAssertEqual(settings.defaultModel, "laya-multilingual")
        XCTAssertEqual(settings.idleUnloadSeconds, 60)
        XCTAssertEqual(settings.device, "cpu")
        XCTAssertEqual(settings.multiLabelThreshold, 0.7, accuracy: 0.0001)
        XCTAssertEqual(settings.fallbackProbabilityFloor, 0.2, accuracy: 0.0001)
    }

    func testAPartialFileKeepsTheDefaults() throws {
        let settings = try JSONDecoder().decode(Settings.self, from: Data("{\"port\": 7000}".utf8))
        XCTAssertEqual(settings.port, 7000)
        XCTAssertEqual(settings.defaultModel, "laya-typed-decisions")
        XCTAssertEqual(settings.idleUnloadSeconds, 900)
    }

    func testTheEncodedKeysUseSnakeCase() throws {
        let data = try JSONEncoder().encode(Settings(apiKey: "k"))
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertNotNil(object["idle_unload_seconds"])
        XCTAssertNotNil(object["default_model"])
        XCTAssertNotNil(object["api_key"])
        XCTAssertNil(object["idleUnloadSeconds"])
    }

    func testARoundTripThroughTheFile() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let store = SettingsStore(directory: directory)
        defer { try? FileManager.default.removeItem(at: directory) }

        XCTAssertEqual(store.load(), Settings())
        var settings = Settings()
        settings.port = 6123
        settings.idleUnloadSeconds = 300
        try store.save(settings)
        XCTAssertEqual(store.load().port, 6123)
        XCTAssertEqual(store.load().idleUnloadSeconds, 300)
    }

    func testABrokenFileFallsBackToTheDefaults() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = SettingsStore(directory: directory)
        try Data("{not json".utf8).write(to: store.fileURL)
        XCTAssertEqual(store.load(), Settings())
    }

    func testTheLocalBaseURLAlwaysUsesLoopback() {
        var settings = Settings()
        settings.host = "0.0.0.0"
        settings.port = 6000
        XCTAssertEqual(settings.localBaseURL.absoluteString, "http://127.0.0.1:6000")
    }

    func testListensOnNetwork() {
        XCTAssertFalse(Settings(host: "127.0.0.1").listensOnNetwork)
        XCTAssertFalse(Settings(host: "localhost").listensOnNetwork)
        XCTAssertTrue(Settings(host: "0.0.0.0").listensOnNetwork)
    }

    func testAGeneratedKeyIsUniqueAndPrefixed() {
        let first = generateAPIKey()
        let second = generateAPIKey()
        XCTAssertTrue(first.hasPrefix("laya-"))
        XCTAssertNotEqual(first, second)
        XCTAssertGreaterThan(first.count, 24)
    }

    func testIdleIntervalSeconds() {
        XCTAssertEqual(IdleInterval.never.seconds, 0)
        XCTAssertEqual(IdleInterval.fifteenMinutes.seconds, 900)
        XCTAssertEqual(IdleInterval.fourHours.seconds, 14400)
    }

    func testIdleIntervalClosest() {
        XCTAssertEqual(IdleInterval.closest(to: 0), .never)
        XCTAssertEqual(IdleInterval.closest(to: -5), .never)
        XCTAssertEqual(IdleInterval.closest(to: 900), .fifteenMinutes)
        XCTAssertEqual(IdleInterval.closest(to: 1000), .fifteenMinutes)
        XCTAssertEqual(IdleInterval.closest(to: 100_000), .fourHours)
    }

    func testEveryModelHasATitle() {
        XCTAssertEqual(Models.all.count, 4)
        XCTAssertTrue(Models.all.contains(Models.default))
        for model in Models.all {
            XCTAssertFalse(Models.title(for: model).isEmpty)
            XCTAssertNotEqual(Models.title(for: model), model)
        }
    }
}

extension SettingsTests {
    func testTheBaseURLShowsAReachableHost() {
        var settings = Settings()
        settings.port = 5292
        XCTAssertEqual(settings.baseURL, "http://127.0.0.1:5292/v1")

        settings.host = "0.0.0.0"
        let url = settings.baseURL
        XCTAssertFalse(url.contains("0.0.0.0"), "A bind to every interface needs a real name.")
        XCTAssertTrue(url.hasSuffix(":5292/v1"))
    }
}
