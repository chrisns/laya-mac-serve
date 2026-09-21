import XCTest

@testable import LayaServeCore

final class ServerStatusTests: XCTestCase {
    func testDecodesTheServerReply() throws {
        let json = """
            {"state":"loaded","model":"laya-typed-decisions","default_model":"laya",
             "device":"mps","loaded_at":1.0,"last_used":2.0,"idle_seconds":3.5,
             "idle_unload_seconds":900,"rss_mb":3154.1,"peak_rss_mb":3200.0,
             "error":null,"fake_model":false,"host":"127.0.0.1","port":5292,
             "api_key_set":false,"exposed_without_key":false}
            """
        let status = try JSONDecoder().decode(ServerStatus.self, from: Data(json.utf8))
        XCTAssertEqual(status.state, "loaded")
        XCTAssertEqual(status.model, "laya-typed-decisions")
        XCTAssertEqual(status.device, "mps")
        XCTAssertEqual(status.rssMB, 3154.1)
        XCTAssertEqual(status.fakeModel, false)
    }

    func testAnUnloadedReply() throws {
        let json = """
            {"state":"unloaded","model":null,"device":"unloaded","idle_seconds":null,
             "idle_unload_seconds":900,"rss_mb":21.2,"error":null}
            """
        let status = try JSONDecoder().decode(ServerStatus.self, from: Data(json.utf8))
        XCTAssertEqual(MenuState.from(status), .unloaded)
    }

    func testNoReplyMeansStarting() {
        XCTAssertEqual(MenuState.from(nil), .starting)
        XCTAssertEqual(MenuState.starting.symbolName, "circle.dotted")
    }

    func testALoadedStateShowsTheModelAndMemory() {
        let state = MenuState.from(
            ServerStatus(state: "loaded", model: "laya", device: "mps", rssMB: 3154.1))
        XCTAssertEqual(state.title, "Loaded laya on mps 3154 MB")
        XCTAssertEqual(state.symbolName, "brain")
    }

    func testAnErrorStateShowsTheMessage() {
        let state = MenuState.from(ServerStatus(state: "error", error: "out of memory"))
        XCTAssertEqual(state, .failed("out of memory"))
        XCTAssertTrue(state.title.contains("out of memory"))
        XCTAssertEqual(state.symbolName, "exclamationmark.triangle")
    }

    func testEveryStateHasANonEmptyTitle() {
        let states: [MenuState] = [
            .starting, .unloaded, .loaded(model: "laya", device: "cpu", rssMB: nil),
            .failed("x"),
        ]
        for state in states {
            XCTAssertFalse(state.title.isEmpty)
            XCTAssertFalse(state.symbolName.isEmpty)
        }
    }
}
