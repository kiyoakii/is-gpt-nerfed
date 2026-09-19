import SwiftUI

/// Label-left / control-right rows, four quiet groups, sentence case throughout.
struct SettingsView: View {
    @Environment(Store.self) private var store
    @Environment(\.plainRendering) private var plain

    private let frequencies: [(String, String)] = [
        ("manual", L10n.tr("Manually")), ("turns:4", L10n.tr("Every 4 turns")), ("turns:8", L10n.tr("Every 8 turns")), ("turns:16", L10n.tr("Every 16 turns")),
        ("15m", L10n.tr("Every 15 min of activity")), ("30m", L10n.tr("Every 30 min of activity")), ("1h", L10n.tr("Every hour of activity")), ("2h", L10n.tr("Every 2 hours of activity")),
    ]
    private let heartbeats: [(String, String)] = [
        ("manual", L10n.tr("Manually")), ("15m", L10n.tr("Every 15 minutes")), ("30m", L10n.tr("Every 30 minutes")), ("1h", L10n.tr("Every hour")), ("2h", L10n.tr("Every 2 hours")), ("6h", L10n.tr("Every 6 hours")),
    ]
    private let modes: [(String, String)] = [("auto", L10n.tr("Probe in the background")), ("nudge", L10n.tr("Only remind me"))]
    private let confidences: [(Double, String)] = [(0.7, "70%"), (0.8, "80%"), (0.9, "90%"), (0.95, "95%")]

    var body: some View {
        let cfg = store.snapshot?.config
        VStack(alignment: .leading, spacing: 14) {
            Group(title: L10n.tr("Schedule")) {
                row(L10n.tr("Probe each active session")) { picker(cfg?.frequency ?? "30m", frequencies, key: "frequency") }
                RowSeparator()
                row(L10n.tr("Fresh-session heartbeat")) { picker(cfg?.freshFrequency ?? "manual", heartbeats, key: "fresh_frequency") }
                RowSeparator()
                row(L10n.tr("When a probe is due")) { picker(cfg?.mode ?? "auto", modes, key: "mode") }
                RowSeparator()
                row(L10n.tr("Forks per probe")) {
                    segments(["1", "2", "3"], selected: String(cfg?.queries ?? 3)) { v in Task { await store.setConfig("queries", v) } }
                        .frame(width: 110)
                }
                RowSeparator()
                row(L10n.tr("Run the forks in parallel")) { toggle("parallel", cfg?.parallel ?? true) }
            }
            Group(title: L10n.tr("Verdict")) {
                row(L10n.tr("Call a mismatch at")) {
                    segments(confidences.map(\.1), selected: label(for: cfg?.mismatchConfidence ?? 0.8)) { v in
                        if let c = confidences.first(where: { $0.1 == v }) { Task { await store.setConfig("mismatch_confidence", String(c.0)) } }
                    }
                    .frame(width: 190)
                }
                RowSeparator()
                row(L10n.tr("Halt the session after a mismatch")) { toggle("halt_on_mismatch", cfg?.haltOnMismatch ?? false) }
                RowSeparator()
                row(L10n.tr("Scan rollouts on every turn")) { toggle("passive", cfg?.passive ?? true) }
                RowSeparator()
                row(L10n.tr("Also ask the server which model answered")) { toggle("served_check", cfg?.servedCheck ?? true) }
            }
            Group(title: L10n.tr("Alerts")) {
                row(L10n.tr("Notifications")) { toggle("notify", cfg?.notify ?? true) }
                RowSeparator()
                row(L10n.tr("Also notify on a match")) { toggle("notify_on_ok", cfg?.notifyOnOk ?? false) }
                RowSeparator()
                row(L10n.tr("Post matches into the session")) { toggle("announce_ok", cfg?.announceOk ?? false) }
                RowSeparator()
                row(L10n.tr("Sound on a downgrade")) { toggle("sound", cfg?.sound ?? true) }
            }
            Group(title: L10n.tr("App")) {
                row(L10n.tr("Hide session titles and account (for screenshots)")) { toggle("hide_titles", cfg?.hideTitles ?? false) }
                RowSeparator()
                row(L10n.tr("Check for updates")) { toggle("check_updates", cfg?.checkUpdates ?? true) }
                RowSeparator()
                row(L10n.tr("Launch at login")) {
                    if plain {
                        PlainSwitch(on: store.launchAtLogin)
                    } else {
                        Toggle("", isOn: Binding(get: { store.launchAtLogin }, set: { store.setLaunchAtLogin($0) }))
                            .toggleStyle(.switch).labelsHidden().controlSize(.mini)
                    }
                }
            }
        }
    }

    // MARK: building blocks

    private func row<Control: View>(_ title: String, @ViewBuilder control: () -> Control) -> some View {
        HStack(spacing: 8) {
            Text(title).font(Type.text).lineLimit(1)
            Spacer(minLength: 8)
            control()
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
    }

    @ViewBuilder
    private func picker(_ current: String, _ options: [(String, String)], key: String) -> some View {
        let fallback = key == "frequency" || key == "fresh_frequency"
            ? L10n.frequency(current, active: key == "frequency") : current
        if plain {
            PlainValue(text: options.first(where: { $0.0 == current })?.1 ?? fallback)
        } else {
            Picker("", selection: Binding(get: { current }, set: { v in Task { await store.setConfig(key, v) } })) {
                ForEach(options, id: \.0) { Text($0.1).tag($0.0) }
                if !options.contains(where: { $0.0 == current }) { Text(fallback).tag(current) }
            }
            .labelsHidden().controlSize(.small).frame(width: 170)
        }
    }

    @ViewBuilder
    private func segments(_ options: [String], selected: String, set: @escaping (String) -> Void) -> some View {
        if plain {
            PlainSegments(options: options, selected: selected)
        } else {
            Picker("", selection: Binding(get: { selected }, set: set)) {
                ForEach(options, id: \.self) { Text($0).tag($0) }
            }
            .pickerStyle(.segmented).labelsHidden().controlSize(.small)
        }
    }

    @ViewBuilder
    private func toggle(_ key: String, _ value: Bool) -> some View {
        if plain {
            PlainSwitch(on: value)
        } else {
            Toggle("", isOn: Binding(get: { value }, set: { v in Task { await store.setConfig(key, v ? "true" : "false") } }))
                .toggleStyle(.switch).labelsHidden().controlSize(.mini)
        }
    }

    private func label(for confidence: Double) -> String {
        confidences.min(by: { abs($0.0 - confidence) < abs($1.0 - confidence) })?.1 ?? "80%"
    }
}
