// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "IsGPTNerfed",
    defaultLocalization: "en",
    platforms: [.macOS("15.0")],
    targets: [
        .executableTarget(
            name: "IsGPTNerfed",
            path: "Sources/IsGPTNerfed",
            resources: [.process("Resources")],
            swiftSettings: [.unsafeFlags(["-Osize"])]
        ),
        .testTarget(
            name: "IsGPTNerfedTests",
            dependencies: ["IsGPTNerfed"]
        )
    ]
)
