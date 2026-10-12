// Passive CoreMIDI listener: because CoreMIDI lets several clients read the same source at once,
// this tool can run next to Lié without taking the Touché's ports away from it.
// Usage: midisniff [substring]   (only sources whose name contains the substring are tapped)
import CoreMIDI
import Foundation

class SniffContext {
    var start = Date()
}

let context = SniffContext()

func endpointName(_ endpoint: MIDIEndpointRef) -> String {
    var name: Unmanaged<CFString>?
    MIDIObjectGetStringProperty(endpoint, kMIDIPropertyDisplayName, &name)
    return name?.takeRetainedValue() as String? ?? "?"
}

func hex(_ bytes: [UInt8]) -> String {
    return bytes.map { String(format: "%02X", $0) }.joined(separator: " ")
}

func printPacketList(_ list: UnsafePointer<MIDIPacketList>, source: String) {
    var packet = list.pointee.packet
    for _ in 0..<list.pointee.numPackets {
        let length = Int(packet.length)
        let bytes = withUnsafeBytes(of: packet.data) { Array($0.prefix(length)) }
        let elapsed = Date().timeIntervalSince(context.start)
        print(String(format: "%9.3f  %@  [%d] %@", elapsed, source, length, hex(bytes)))
        fflush(stdout)
        packet = MIDIPacketNext(&packet).pointee
    }
}

let filter = CommandLine.arguments.count > 1 ? CommandLine.arguments[1].lowercased() : ""

var client = MIDIClientRef()
MIDIClientCreate("midisniff" as CFString, nil, nil, &client)

var port = MIDIPortRef()
MIDIInputPortCreateWithBlock(client, "in" as CFString, &port) { list, refCon in
    let source = refCon.map { Unmanaged<NSString>.fromOpaque($0).takeUnretainedValue() as String } ?? "?"
    printPacketList(list, source: source)
}

print("Sources:")
for index in 0..<MIDIGetNumberOfSources() {
    let source = MIDIGetSource(index)
    let name = endpointName(source)
    let tapped = filter.isEmpty || name.lowercased().contains(filter)
    print("  \(tapped ? "*" : " ") \(name)")
    if tapped {
        let label = Unmanaged.passRetained(name as NSString).toOpaque()
        MIDIPortConnectSource(port, source, label)
    }
}
print("Listening (Ctrl-C to stop)...")
RunLoop.main.run()
