import Foundation

/// Mirrors the JSON produced by `nerfed snapshot --json` (snake_case keys, decoded with convertFromSnakeCase).
struct Snapshot: Codable {
    var generated: String
    var version: String
    var nerfedBin: String?
    var ledger: String?
    var config: DGCConfig
    var hooksLastEvent: String?
    var hooksLastEventAgo: String?
    var hooks: HooksInfo?
    var install: InstallInfo?
    var update: UpdateInfo?
    var freshDue: Bool?
    var overall: Overall
    var defaultModel: String?
    var defaultEffort: String?
    var globalProbe: ProbeSummary?
    var globalRunning: Bool?
    var globalAlert: Bool?
    var globalProbes: [ProbeSummary]?
    var globalReportText: String?
    var globalFailure: ProbeSummary?     // a failed fresh-session attempt newer than the last verdict (Retry)
    var globalUpgraded: Bool?
    var lastVerdict: ProbeSummary?       // the newest probe of any kind that produced a verdict
    var account: AccountInfo?
    var threads: [ThreadInfo]
    var recentProbes: [ProbeSummary]
    var demo: Bool?
}

struct AccountInfo: Codable {
    var label: String?
    var plan: String?
    var switchedAt: String?
    var switchedAgo: String?
    var previousLabel: String?
}

/// The daily release check (one request to GitHub for the latest tag; `nerfed update-check`).
struct UpdateInfo: Codable {
    var current: String?
    var latest: String?
    var available: Bool?
    var url: String?
    var checkedAgo: String?
    var error: String?
    var enabled: Bool?
    var status: String?      // downloading | installed | failed: …
    var hasArchive: Bool?
}

/// Whether the plugin (bundled in this app or from a checkout) is registered with Codex.
struct InstallInfo: Codable {
    var pluginEnabled: Bool?
    var codexFound: Bool?
    var marketplaceRoot: String?
    var bundled: Bool?
}

/// Trust state of the plugin's hooks as Codex reports it, and whether the desktop app has ever fired them.
struct HooksInfo: Codable {
    var checked: String?
    var checkedAgo: String?
    var total: Int?
    var trusted: Int?
    var untrusted: Int?
    var state: String?          // trusted | untrusted | missing | unknown
    var error: String?
    var lastDesktopEvent: String?
    var lastDesktopEventAgo: String?
    var desktopLoaded: Bool?
    var installedAgo: String?
    var desktopLoadedCurrent: Bool?
    var staleSinceInstallS: Double?
}

struct Overall: Codable {
    var status: String
    var downgraded: Int
    var suspicious: Int?
    var upgraded: Int?
    var unverified: Int?
    var running: Int
    var message: String
}

struct DGCConfig: Codable {
    var frequency: String
    var mode: String
    var queries: Int
    var parallel: Bool
    var languages: [String]
    var passive: Bool
    var notify: Bool
    var notifyOnOk: Bool
    var announceOk: Bool
    var sound: Bool
    var haltOnMismatch: Bool
    var mismatchConfidence: Double?
    var confirmUncertain: Bool?
    var hideTitles: Bool?
    var freshFrequency: String?
    var checkUpdates: Bool?
    var servedCheck: Bool?
}

struct ThreadInfo: Codable, Identifiable {
    var id: String
    var title: String
    var cwd: String?
    var model: String?
    var effort: String?
    var updated: String?
    var updatedAgo: String?
    var active: Bool
    var alert: Bool
    var suspicious: Bool?
    var unverified: Bool?
    var turns: Int
    var turnsSinceProbe: Int
    var due: Bool
    var probeRunning: Bool
    var probeNote: String?
    var halted: Bool
    var requested: Bool
    var hardEvidence: Int
    var softEvidence: Int
    var evidenceHistory: Int?
    var lastEvidence: String?
    var lastEvidenceAgo: String?
    var lastEvidenceSeverity: String?    // hard | soft | good: what the row's evidence line is about
    var goodEvidence: Int?
    var upgraded: Bool?                  // moved to a better model (a rollout): good news
    var lastProbe: ProbeSummary?         // the verdict: the newest probe that produced one
    var lastFailure: ProbeSummary?       // a failed attempt newer than that verdict: only asks for Retry
    var probes: [ProbeSummary]?          // this thread's probe history, newest first (the in-place report)
    var evidence: [EvidenceInfo]?        // hard and soft findings, newest first, reverted ones included
    var reportText: String?              // plain text of the report, for the clipboard
}

/// One scanner finding as the panel shows it; `active` is false once a later change reverted it.
struct EvidenceInfo: Codable, Identifiable {
    var text: String
    var ts: String?
    var ago: String?
    var severity: String?
    var active: Bool?
    var id: String { (ts ?? "") + text }
}

/// One row of the fingerprint attribution ("gpt-5.6-luna 91%").
struct Attribution: Codable, Hashable {
    var model: String?
    var probability: Double?
}

struct ProbeSummary: Codable, Identifiable {
    var id: String
    var threadId: String?
    var mode: String?
    var status: String?
    var finished: String?
    var finishedAgo: String?
    var verdict: String?
    var direction: String?
    var expected: String?
    var prediction: String?
    var probability: Double?
    var pExpected: Double?
    var margin: Double?
    var confidence: String?
    var usedOutputs: Int?
    var queries: Int?
    var rounds: Int?
    var elapsedS: Double?
    var errors: [String]?
    var quote: String?
    var isDowngrade: Bool?
    var isUpgrade: Bool?
    var isSuspicious: Bool?
    var staleAccount: Bool?
    var accountState: String?   // current | other | unknown
    var retryable: Bool?
    var retries: Int?
    var results: [Attribution]?
    var serverModel: String?      // the model the server named for this probe's model (served_check); nil when it did not run
    var serverState: String?      // same | downgrade | upgrade | lateral | unrecognized | failed
    var serverRequested: String?
    var serverError: String?
    var started: String?

    static func pct(_ p: Double?) -> String {
        guard let p else { return "" }
        return "\(Int((p * 100).rounded()))%"
    }

    var probabilityText: String { Self.pct(probability) }
}
