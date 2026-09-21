// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "LayaServe",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "LayaServeCore"),
        .executableTarget(name: "LayaServe", dependencies: ["LayaServeCore"]),
        .testTarget(name: "LayaServeCoreTests", dependencies: ["LayaServeCore"]),
    ]
)
