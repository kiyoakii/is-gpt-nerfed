import SwiftUI

// MARK: - Verdict presentation: one coloured word, no pills, no icons. The only colours in the panel are the
// semantic ones (green / orange / red) on dots, verdict words and evidence lines.

extension ProbeSummary {
    var tint: Color {
        if isDowngrade == true { return .red }
        if isUpgrade == true { return .green }
        switch verdict {
        case "MATCH": return .green
        case "MISMATCH", "SUSPICIOUS": return .orange
        default: return .secondary
        }
    }

    /// Sentence-case verdict word; the direction carries the meaning ("Downgrade" rather than "Mismatch · downgrade").
    var word: String {
        guard let v = verdict else { return L10n.tr(status == "failed" ? "Failed" : "…") }
        switch (v, direction) {
        case ("DOWNGRADED!", _): return L10n.tr("Downgraded")
        case ("MISMATCH", "downgrade"?): return L10n.tr("Downgrade")
        case ("MISMATCH", "upgrade"?): return L10n.tr("Upgrade")
        case ("MISMATCH", _): return L10n.tr("Rerouted")
        case ("SUSPICIOUS", _): return L10n.tr("Suspicious")
        case ("MATCH", _): return L10n.tr("Match")
        case ("UNLISTED", _): return L10n.tr("Unlisted")
        case ("INVALID", _): return L10n.tr("Invalid")
        default: return v.capitalized
        }
    }

    var isFailure: Bool { verdict == "INVALID" || status == "failed" }

    /// The server named a known model other than the one asked for: worth a word in the row, not only in the report.
    var serverNamedOther: Bool { serverModel != nil && ["downgrade", "lateral", "upgrade"].contains(serverState ?? "") }

    /// "gpt-5.6-luna 91%, declared 3% · 2 rounds · retried once"
    var detail: String {
        var parts: [String] = []
        if isFailure {
            parts.append(errors?.first.map { L10n.backend($0) } ?? L10n.tr("no usable sample"))
        } else if staleAccount == true {
            parts.append(prediction ?? "?")  // unverified for this account: the numbers would only lend false weight
        } else {
            // The server's answer leads when it made the verdict (a narrow row truncates the end), follows otherwise.
            let server = serverNamedOther ? serverModel.map { L10n.tr("server: %@", $0) } : nil
            if direction == "server", let server { parts.append(server) }
            if prediction != nil || server == nil {  // a verdict the server reached without answers has no fingerprint to show
                var s = prediction ?? "?"
                if !probabilityText.isEmpty { s += " \(probabilityText)" }
                if let e = expected, e != prediction, let pe = pExpected { s += ", \(L10n.tr("declared %@", Self.pct(pe)))" }
                parts.append(s)
            }
            if direction != "server", let server { parts.append(server) }
            if let n = usedOutputs, let q = queries, n < q { parts.append(L10n.tr("%@ of %@ answers", String(n), String(q))) }
            if let r = rounds, r > 1 { parts.append(L10n.tr("%@ rounds", String(r))) }
        }
        if let r = retries, r > 0 { parts.append(r == 1 ? L10n.tr("retried once") : L10n.tr("retried %@×", String(r))) }
        return parts.joined(separator: " · ")
    }
}

private func petFace(alert: Bool, warn: Bool, running: Bool) -> String {
    if alert { return "(ಠ_ಠ)" }
    if warn { return "(•_•)" }
    if running { return "(•o•)" }
    return "(•ᴗ•)"
}

/// The chip face that matches the app icon (bundled as face-ok / face-warn / face-alert.png); text fallback.
struct FaceView: View {
    let alert: Bool
    let warn: Bool
    let running: Bool
    var size: CGFloat = 72

    private var image: NSImage? {
        let name = alert ? "face-alert" : (warn ? "face-warn" : "face-ok")
        guard let res = Bundle.main.resourcePath else { return nil }
        return NSImage(contentsOfFile: res + "/\(name).png")
    }

    var body: some View {
        if let img = image {
            Image(nsImage: img).resizable().interpolation(.high).frame(width: size, height: size)
        } else {
            Text(petFace(alert: alert, warn: warn, running: running))
                .font(.system(size: 17, weight: .semibold, design: .rounded))
                .frame(width: size + 8, height: size - 8)
                .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
    }
}

/// "Match · gpt-6-astra 100% · 10h ago" as one line, verdict word coloured. A verdict from another account is not
/// one for this account: "Unverified · Match, another account · 10h ago".
struct VerdictLine: View {
    let probe: ProbeSummary
    var body: some View {
        let stale = probe.staleAccount == true
        HStack(spacing: 4) {
            if stale {
                Text(L10n.tr("Unverified")).font(Type.strong).foregroundStyle(.secondary)
                Text("·").foregroundStyle(.tertiary)
                Text(probe.accountState == "unknown"
                     ? L10n.tr("%@, account unknown", probe.word)
                     : L10n.tr("%@, another account", probe.word))
                    .foregroundStyle(.tertiary).lineLimit(1)
                    .help(probe.accountState == "unknown"
                          ? L10n.tr("Recorded before accounts were tracked, so it cannot vouch for the signed-in account. Re-probed when the session is next active.")
                          : L10n.tr("Probed while a different Codex account was signed in; it does not vouch for this account. Re-probed when the session is next active."))
            } else {
                Text(probe.word).font(Type.strong).foregroundStyle(probe.tint)
                Text("·").foregroundStyle(.tertiary)
                Text(probe.detail).foregroundStyle(.secondary).lineLimit(1)
            }
            if let ago = L10n.ago(probe.finishedAgo), !ago.isEmpty {
                Text("·").foregroundStyle(.tertiary)
                Text(ago).monospacedDigit().foregroundStyle(.tertiary)
            }
        }
        .font(Type.text)
        .help(probe.errors?.isEmpty == false
              ? probe.errors!.map { L10n.backend($0) }.joined(separator: "\n")
              : L10n.backend(probe.quote ?? ""))
    }
}

// MARK: - Panel

struct PanelView: View {
    @Environment(Store.self) private var store
    @Environment(\.plainRendering) private var plain
    @State private var showSettings: Bool
    @State private var open: String?        // the row showing its report in place: a thread id, or "fresh"
    @State private var listHeight: CGFloat = 0

    init(showSettings: Bool = false, open: String? = nil) {
        _showSettings = State(initialValue: showSettings)
        _open = State(initialValue: open)
    }

    var body: some View {
        VStack(spacing: 14) {
            header
            if showSettings {  // a page of its own: it replaces the lists rather than stacking under them
                SettingsView().transition(.opacity.combined(with: .move(edge: .trailing)))
            } else {
                setup
                threads
                fresh
            }
            footer
        }
        .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 10)
        .frame(width: 420)
        .task { store.start() }
        .onAppear { Task { await store.refresh() } }
    }

    private func toggle(_ id: String) {
        withAnimation(.snappy(duration: 0.25)) { open = (open == id) ? nil : id }
    }

    // MARK: header

    // A centred hero: the face over the headline of the moment (17 pt), the other counts, the last probe and the
    // quiet facts, so the header is balanced whatever the length of the headline.
    private var header: some View {
        let parts = statusWord.components(separatedBy: " · ")
        return VStack(spacing: 3) {
            FaceView(alert: store.isAlert, warn: store.isWarn, running: store.isRunning)
                .padding(.bottom, 5)
            Text(parts.first ?? "")
                .font(Type.headline)
                .foregroundStyle(store.isAlert ? .red : (store.isWarn ? .orange : (store.isUpgraded ? .green : .primary)))
                .lineLimit(2)
                .multilineTextAlignment(.center)
            if parts.count > 1 {
                Text(parts.dropFirst().joined(separator: " · ")).font(Type.text).foregroundStyle(.secondary).lineLimit(1)
            }
            if let (text, attention) = hooksLine, attention {
                Text(text).font(Type.strong).foregroundStyle(.orange).lineLimit(2).multilineTextAlignment(.center)
            }
            lastProbeLine
            if !quietLines.isEmpty {
                Text(quietLines.joined(separator: " · ")).font(Type.text).foregroundStyle(.tertiary).lineLimit(2).multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 2)
    }

    /// "Last probe · Match · 49m ago": the newest verdict of any thread or fresh session.
    @ViewBuilder private var lastProbeLine: some View {
        if let p = store.snapshot?.lastVerdict, store.lastError == nil {
            HStack(spacing: 4) {
                Text(L10n.tr("Last probe")).foregroundStyle(.tertiary)
                Text("·").foregroundStyle(.tertiary)
                Text(p.staleAccount == true ? L10n.tr("Unverified") : p.word).font(Type.strong).foregroundStyle(p.staleAccount == true ? Color.secondary : p.tint)
                if let ago = L10n.ago(p.finishedAgo), !ago.isEmpty {
                    Text("·").foregroundStyle(.tertiary)
                    Text(ago).monospacedDigit().foregroundStyle(.tertiary)
                }
            }
            .font(Type.text)
        }
    }

    private var statusWord: String {
        if let err = store.lastError { return L10n.tr("nerfed error: %@", L10n.backend(err)) }
        guard let s = store.snapshot else { return L10n.tr("Loading…") }
        return L10n.statusMessage(s.overall.message)
    }

    /// "w…@example.com", "hooks alive 12s ago", "account switched 45m ago": one line each, only when there is something to say.
    private var quietLines: [String] {
        guard let s = store.snapshot, store.lastError == nil else { return [] }
        var out: [String] = []
        if let acct = s.account?.label, !acct.isEmpty {
            out.append(s.config.hideTitles == true ? L10n.tr(acct) : acct)
        }
        if let (text, attention) = hooksLine, !attention { out.append(text) }
        if let ago = L10n.ago(s.account?.switchedAgo), !ago.isEmpty { out.append(L10n.tr("account switched %@", ago)) }
        return out
    }

    /// Hook plumbing state; attention = true whenever Codex will not run the hooks yet.
    private var hooksLine: (String, Bool)? {
        guard let s = store.snapshot, store.lastError == nil else { return nil }
        guard let h = s.hooks else {
            if let ago = L10n.ago(s.hooksLastEventAgo), !ago.isEmpty { return (L10n.tr("hooks alive %@", ago), false) }
            return (L10n.tr("no hook events yet"), false)
        }
        switch h.state {
        case "untrusted":
            return (L10n.tr("Hooks not trusted by Codex · run nerfed hooks trust"), true)
        case "missing":
            return (L10n.tr("Codex does not list the plugin's hooks · run install.sh"), true)
        default:
            if h.desktopLoaded != true {
                return (L10n.tr("Codex has not loaded the plugin yet · quit and reopen Codex"), true)
            }
            if h.desktopLoadedCurrent != true, let stale = h.staleSinceInstallS, stale > 240 {
                return (L10n.tr("Codex still runs the previous version · quit and reopen Codex"), true)
            }
            return (L10n.tr("hooks alive %@", L10n.ago(h.lastDesktopEventAgo) ?? L10n.tr("just now")), false)
        }
    }

    // MARK: first-run setup (only while something is missing)

    @ViewBuilder private var setup: some View {
        if let s = store.snapshot, store.lastError == nil, let inst = s.install {
            if inst.codexFound == false {
                setupRow(L10n.tr("Codex is not installed on this Mac. Install the Codex app, then reopen this panel."), button: nil)
            } else if inst.pluginEnabled == false {
                setupRow(L10n.tr("The plugin is not registered with Codex yet. Install adds the bundled plugin and records hook trust."),
                         button: store.installing ? nil : L10n.tr("Install")) { Task { await store.installPlugin() } }
            } else if s.hooks?.state == "untrusted" {
                setupRow(L10n.tr("Codex has not been told to trust the plugin's hooks, so nothing runs in your sessions yet."),
                         button: L10n.tr("Trust hooks")) { Task { await store.trustHooks() } }
            }
        }
    }

    private func setupRow(_ text: String, button: String?, action: @escaping () -> Void = {}) -> some View {
        Group(title: L10n.tr("Setup")) {
            HStack(alignment: .center, spacing: 10) {
                Circle().fill(Color.orange).frame(width: 7, height: 7)
                Text(text).font(Type.text).foregroundStyle(.secondary).lineLimit(3)
                Spacer(minLength: 8)
                if store.installing {
                    ProgressView().controlSize(.small)
                } else if let button {
                    RowButton(title: button, action: action)
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 8)
        }
    }

    // MARK: threads

    private var threads: some View {
        let list = store.snapshot?.threads ?? []
        let trailing = list.isEmpty ? nil : L10n.tr("%@ in 48 h", String(list.count))
        return Group(title: L10n.tr("Active sessions"), trailing: trailing) {
            if list.isEmpty {
                Text(store.snapshot == nil ? L10n.tr("Reading the ledger…") : L10n.tr("No Codex sessions in the last 48 hours."))
                    .font(Type.text).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 40)
            } else if plain {  // offscreen self-portrait: ScrollView does not render
                VStack(spacing: 0) {
                    ForEach(Array(list.prefix(6).enumerated()), id: \.element.id) { i, t in
                        if i > 0 { RowSeparator() }
                        ThreadRow(thread: t, isOpen: open == t.id) { toggle(t.id) }
                    }
                }
            } else {
                // A ScrollView inside a self-sizing popover collapses to zero height, so size it from the
                // measured content height (capped) instead of letting the layout guess.
                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(Array(list.enumerated()), id: \.element.id) { i, t in
                            if i > 0 { RowSeparator() }
                            ThreadRow(thread: t, isOpen: open == t.id) { toggle(t.id) }
                        }
                    }
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { listHeight = $0 }
                }
                .frame(height: min(open == nil ? 340 : 460, max(listHeight, 56)))
                .animation(.snappy(duration: 0.25), value: listHeight)
            }
        }
    }

    // MARK: fresh session (global probe)

    private var fresh: some View {
        let snap = store.snapshot
        let running = snap?.globalRunning ?? false
        let last = snap?.globalProbe
        let failure = snap?.globalFailure
        let model = snap?.defaultModel ?? L10n.tr("default model")
        let effort = snap?.defaultEffort.map { " @ \($0)" } ?? ""
        return Group(title: L10n.tr("Fresh session"), trailing: model + effort) {
            let history = snap?.globalProbes ?? (last.map { [$0] } ?? [])
            ExpandableRow(canOpen: ReportLines.hasContent(probes: history, evidence: [], failure: failure), toggle: { toggle("fresh") }) {
                HStack(alignment: .top, spacing: 8) {
                    Circle().fill(last.map { ($0.isFailure || $0.staleAccount == true) ? Color.secondary.opacity(0.35) : $0.tint } ?? Color.secondary.opacity(0.35))
                        .frame(width: 7, height: 7).padding(.top, 4)
                    SwapLines(isOpen: open == "fresh") {
                        if running {
                            HStack(spacing: 5) {
                                ProgressView().controlSize(.mini)
                                Text(L10n.tr("Probing %@ new ephemeral sessions…", String(snap?.config.queries ?? 3))).font(Type.text).foregroundStyle(.secondary)
                            }
                        } else if let p = last {
                            VerdictLine(probe: p)
                        } else {
                            Text(L10n.tr("Never probed · a brand-new session, no history")).font(Type.text).foregroundStyle(.secondary)
                        }
                    } report: {
                        ReportLines(probes: history, evidence: [], failure: failure)
                    }
                    Spacer(minLength: 8)
                    if !running {
                        RowButton(title: failure?.retryable == true ? L10n.tr("Retry") : L10n.tr("Probe")) { store.probeFresh() }
                            .help(L10n.tr("Start brand-new ephemeral sessions and fingerprint what a new session gets"))
                    }
                }
                .padding(.horizontal, 10).padding(.vertical, 7)
            }
            .contextMenu {
                if !running { Button(failure?.retryable == true ? L10n.tr("Retry the probe") : L10n.tr("Probe now")) { store.probeFresh() } }
                if let r = snap?.globalReportText {
                    Button(L10n.tr("Copy report")) {
                        store.copy(L10n.report(r, title: "Fresh session", displayTitle: L10n.tr("Fresh session")))
                    }
                }
            }
        }
    }

    // MARK: footer

    private var footer: some View {
        HStack(spacing: 16) {
            TextButton(title: showSettings ? L10n.tr("Done") : L10n.tr("Settings")) { withAnimation(.snappy(duration: 0.25)) { showSettings.toggle() } }
            Spacer()
            if store.updating {
                Text(L10n.tr("Updating…")).font(Type.text).foregroundStyle(.secondary)
            } else if let u = store.snapshot?.update, u.available == true, let latest = u.latest {
                let failed = (u.status ?? "").hasPrefix("failed")
                if u.hasArchive == true {
                    TextButton(title: failed ? L10n.tr("Update failed · retry") : L10n.tr("v%@ is out · update", latest), color: .primary) { store.installUpdate() }
                        .help(failed ? L10n.backend(u.status ?? "") : L10n.tr("Downloads v%@, replaces this app and relaunches it. The previous copy goes to the Trash.", latest))
                } else {  // a release without a zip: open the page
                    TextButton(title: L10n.tr("v%@ is out", latest), color: .primary) { store.openURL(u.url ?? "https://github.com/kiyoakii/is-gpt-nerfed/releases") }
                }
            } else if let v = store.snapshot?.version {
                Text("v\(v)" + (store.snapshot?.demo == true ? L10n.tr(" · sample data") : "")).font(Type.text).foregroundStyle(.tertiary)
            }
            TextButton(title: L10n.tr("Quit")) { NSApplication.shared.terminate(nil) }
        }
        .padding(.horizontal, 2)
    }
}

// MARK: - Rows that open in place

/// A clickable row. Its content decides what to show for the open state; the row adds the hover tint, the link
/// pointer and the click (the row's own button keeps its own click). Rows with nothing to report do not open.
struct ExpandableRow<Content: View>: View {
    @Environment(\.plainRendering) private var plain
    let canOpen: Bool
    let toggle: () -> Void
    @ViewBuilder let content: () -> Content
    @State private var hovered = false

    var body: some View {
        content()
            .contentShape(Rectangle())
            .onTapGesture { if canOpen { toggle() } }
            .clipped()
            .background(hovered && canOpen && !plain ? Color.primary.opacity(0.035) : Color.clear)
            .onHover { hovered = $0 }
            .pointerStyle(canOpen ? .link : .default)
    }
}

/// The lines under a title swap between the summary and the report: the summary slides out to the left, the
/// report slides in from the right, in the same place. Only this row changes height.
struct SwapLines<Summary: View, Report: View>: View {
    let isOpen: Bool
    @ViewBuilder let summary: () -> Summary
    @ViewBuilder let report: () -> Report

    var body: some View {
        if isOpen {
            report().transition(.move(edge: .trailing).combined(with: .opacity))
        } else {
            summary().transition(.move(edge: .leading).combined(with: .opacity))
        }
    }
}

/// The report: last verdict, fingerprint, earlier probes, evidence with what was reverted. Text only; Copy report is in the row's context menu.
struct ReportLines: View {
    @Environment(Store.self) private var store
    let probes: [ProbeSummary]
    let evidence: [EvidenceInfo]
    var failure: ProbeSummary? = nil

    static func hasContent(probes: [ProbeSummary], evidence: [EvidenceInfo], failure: ProbeSummary? = nil) -> Bool {
        !probes.isEmpty || !evidence.isEmpty || failure != nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            if let p = probes.first {
                VerdictLine(probe: p)
                if let r = p.results, !r.isEmpty, !p.isFailure, p.staleAccount != true {
                    fact(L10n.tr("Fingerprint"), r.map { "\($0.model ?? "?") \(ProbeSummary.pct($0.probability))" }.joined(separator: " · "))
                }
                if let state = p.serverState, p.staleAccount != true {
                    fact(L10n.tr("Server"), serverValue(p), tint: serverTint(state))
                }
                ForEach(Array((p.errors ?? []).enumerated()), id: \.offset) { _, e in
                    fact(L10n.tr("Problem"), L10n.backend(e), tint: .orange)
                }
                if p.staleAccount == true {
                    fact(L10n.tr("Account"), p.accountState == "unknown"
                         ? L10n.tr("recorded before accounts were tracked; it cannot vouch for the signed-in account")
                         : L10n.tr("probed under another Codex account; it does not vouch for this one"))
                }
            } else {
                Text(L10n.tr("No probe yet")).foregroundStyle(.tertiary)
            }
            if let f = failure {  // the tool's own failure, not a verdict: what went wrong, and when
                fact(L10n.tr("Attempt"), failureDetail(f))
            }
            ForEach(Array(probes.dropFirst().prefix(4))) { p in
                HStack(spacing: 4) {
                    Text(L10n.tr("Earlier")).foregroundStyle(.tertiary)
                    Text("·").foregroundStyle(.tertiary)
                    VerdictLine(probe: p)
                }
            }
            ForEach(evidence) { e in
                let on = e.active ?? true
                Text(L10n.evidenceText(e.text, ago: e.ago, active: on))
                    .foregroundStyle(on ? (e.severity == "hard" ? Color.red : (e.severity == "soft" ? Color.orange : Color.green)) : Color.secondary)
                    .lineLimit(2)
            }
        }
        .font(Type.text)
        .foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func fact(_ label: String, _ value: String, tint: Color = .secondary) -> some View {
        HStack(alignment: .top, spacing: 4) {
            Text(label).foregroundStyle(.tertiary).frame(width: 64, alignment: .leading)
            Text(value).foregroundStyle(tint).lineLimit(3)
        }
    }

    /// What the server said about the model the probe asked for (served_check). It is weighed next to the fingerprint.
    private func serverValue(_ p: ProbeSummary) -> String {
        let model = p.serverModel ?? "?"
        let asked = p.serverRequested ?? p.expected ?? "?"
        switch p.serverState {
        case "failed": return L10n.tr("no answer: %@", p.serverError.map { L10n.backend($0) } ?? "?")
        case "same": return L10n.tr("%@, as asked", model)
        case "unrecognized": return L10n.tr("%@, asked for %@ · unknown name, not counted", model, asked)
        default: return L10n.tr("%@, asked for %@", model, asked)
        }
    }

    private func serverTint(_ state: String) -> Color {
        switch state {
        case "downgrade": return .red
        case "lateral": return .orange
        case "upgrade": return .green
        default: return .secondary
        }
    }

    private func failureDetail(_ failure: ProbeSummary) -> String {
        var attempt = L10n.tr("failed")
        if let ago = L10n.ago(failure.finishedAgo), !ago.isEmpty { attempt += " \(ago)" }
        var details = [attempt, failure.errors?.first.map { L10n.backend($0) } ?? L10n.tr("no usable answer")]
        if let retries = failure.retries, retries > 0 {
            details.append(retries == 1 ? L10n.tr("retried once") : L10n.tr("retried %@×", String(retries)))
        }
        return details.joined(separator: " · ")
    }

}

/// The finding with its time when that fits on one line; without the time otherwise (a lone "9m ago" on a second
/// line is worse than no time; the report in the open row has it).
struct EvidenceLine: View {
    let text: String
    let ago: String?
    let color: Color

    var body: some View {
        ViewThatFits(in: .horizontal) {
            Text(L10n.evidenceText(text, ago: ago, active: true)).lineLimit(1).fixedSize(horizontal: true, vertical: false)
            Text(L10n.backend(text)).lineLimit(2)
        }
        .font(Type.text).foregroundStyle(color)
    }
}

// MARK: - Thread row
//
//   ● Title                                        ┌───────┐
//     model @ effort · N turns · active 2m ago     │ Probe │   ← one action, vertically centred
//     Match · gpt-6-astra 100% · 5m ago            └───────┘
//     Evidence: … (only when there is any)
//     ┄ report, when the row is open ┄

struct ThreadRow: View {
    @Environment(Store.self) private var store
    let thread: ThreadInfo
    let isOpen: Bool
    let toggle: () -> Void

    private var dot: Color {
        if thread.alert { return .red }
        if thread.suspicious == true { return .orange }
        if thread.upgraded == true { return .green }
        if thread.unverified == true { return .secondary.opacity(0.35) }
        if let p = thread.lastProbe, p.verdict == "MATCH" { return .green }
        return .secondary.opacity(0.35)
    }

    private var history: [ProbeSummary] { thread.probes ?? (thread.lastProbe.map { [$0] } ?? []) }

    var body: some View {
        ExpandableRow(canOpen: ReportLines.hasContent(probes: history, evidence: thread.evidence ?? [], failure: thread.lastFailure), toggle: toggle) {
            HStack(alignment: .center, spacing: 10) {
                HStack(alignment: .top, spacing: 8) {
                    Circle().fill(dot).frame(width: 7, height: 7).padding(.top, 5)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(L10n.sessionTitle(thread.title, isDemo: store.snapshot?.demo == true,
                                               isHidden: store.snapshot?.config.hideTitles == true))
                            .font(Type.title).lineLimit(1)
                        SwapLines(isOpen: isOpen) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(meta).font(Type.text).foregroundStyle(.secondary).lineLimit(1)
                                if thread.probeRunning {
                                    HStack(spacing: 5) {
                                        ProgressView().controlSize(.mini)
                                        let text = thread.probeNote.map { L10n.tr("Probing · %@…", L10n.backend($0)) }
                                            ?? L10n.tr("Probing, ephemeral forks in flight…")
                                        Text(text).font(Type.text).foregroundStyle(.secondary)
                                    }
                                } else if let p = thread.lastProbe {
                                    VerdictLine(probe: p)
                                } else {
                                    Text(thread.due ? L10n.tr("No probe yet · due") : L10n.tr("No probe yet")).font(Type.text).foregroundStyle(.tertiary)
                                }
                                if let ev = thread.lastEvidence, let sev = thread.lastEvidenceSeverity {
                                    EvidenceLine(text: ev, ago: thread.lastEvidenceAgo, color: sev == "hard" ? .red : (sev == "soft" ? .orange : .green))
                                        .help(sev == "good"
                                              ? L10n.tr("Codex's own records show a switch to a better model (a rollout). Good news, still in effect. Click the row for the history.")
                                              : sev == "hard"
                                              ? L10n.tr("Found in the session's own records, independent of any probe, and still in effect. Click the row for the history.")
                                              : L10n.tr("Applied through the session's settings and still in effect: either you changed it, or Codex did (it lowers effort automatically at usage limits). Click the row for the history."))
                                }
                            }
                        } report: {
                            ReportLines(probes: history, evidence: thread.evidence ?? [], failure: thread.lastFailure)
                        }
                    }
                }
                Spacer(minLength: 8)
                action
            }
            .padding(.horizontal, 10).padding(.vertical, 8)
        }
        .contextMenu {
            if !thread.probeRunning, !thread.halted {
                Button(thread.lastFailure?.retryable == true ? L10n.tr("Retry the probe") : L10n.tr("Probe now")) { store.probe(thread) }
            }
            if let r = thread.reportText {
                Button(L10n.tr("Copy report")) {
                    let title = L10n.sessionTitle(thread.title, isDemo: store.snapshot?.demo == true,
                                                  isHidden: store.snapshot?.config.hideTitles == true)
                    store.copy(L10n.report(r, title: thread.title, displayTitle: title))
                }
            }
            if let cwd = thread.cwd, !cwd.isEmpty, FileManager.default.fileExists(atPath: cwd) {
                Button(L10n.tr("Open folder in Finder")) { store.reveal(cwd) }
            }
        }
    }

    private var meta: String {
        var parts = ["\(thread.model ?? "?")\(thread.effort.map { " @ \($0)" } ?? "")"]
        if thread.turns > 0 { parts.append(thread.turns == 1 ? L10n.tr("1 turn") : L10n.tr("%@ turns", String(thread.turns))) }
        if thread.halted { parts.append(L10n.tr("halted")) }
        if let ago = L10n.ago(thread.updatedAgo), !ago.isEmpty { parts.append(L10n.tr("active %@", ago)) }
        return parts.joined(separator: " · ")
    }

    @ViewBuilder private var action: some View {
        if thread.probeRunning {
            EmptyView()
        } else if thread.halted {
            RowButton(title: L10n.tr("Resume"), destructive: true) { Task { await store.resume(thread) } }
                .help(L10n.tr("Clear the halt (work tools are denied in this session)"))
        } else {
            RowButton(title: thread.lastFailure?.retryable == true ? L10n.tr("Retry") : L10n.tr("Probe")) { store.probe(thread) }
                .help(L10n.tr("Fork this session ephemerally (3 parallel forks) and fingerprint the answering model"))
        }
    }
}
