// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmniServ",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "OmniServ",
            path: "Sources/OmniServ"
        )
    ]
)
