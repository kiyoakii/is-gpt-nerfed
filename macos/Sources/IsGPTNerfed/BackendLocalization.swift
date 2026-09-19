import Foundation

/// Presentation-only translations for complete strings emitted by `nerfed` and its app-server client.
/// Dynamic model names, effort identifiers, session titles, IDs, and unknown external text stay untouched.
extension L10n {
    private static let backendEnglishBundle: Bundle = {
        guard let path = resources.path(forResource: "en", ofType: "lproj"),
              let bundle = Bundle(path: path) else { return resources }
        return bundle
    }()

    private static let backendPatterns: [String: NSRegularExpression] = [
        "session-title": #"^Session (\d+)$"#,
        "quote-mismatch-downgrade-a": #"^🎉 Congrats! You've been nerfed! You asked for (\S+); the fingerprint says (\S+) \((\d+%), (\d+)/(\d+) answers\)\. Enjoy the discount you didn't ask for\.$"#,
        "quote-mismatch-downgrade-b": #"^Great news: your (\S+) session is answering like (\S+) \((\d+%)\)\. Nobody told you, but somebody saved money\. Congrats!$"#,
        "quote-mismatch-upgrade": #"^Congrats! You've been secretly upgraded: you asked for (\S+), the fingerprint says (\S+) \((\d+%)\)\. Don't tell anyone\.$"#,
        "quote-mismatch-lateral": #"^Congrats! You've been… re-routed\. You asked for (\S+), the fingerprint says (\S+) \((\d+%)\)\. Same tier, different brain\.$"#,
        "quote-downgraded-hard": #"^🎉 Congrats! You've been nerfed! Codex's own records say so: (.+?)\. No notice, no refund, no shame\.$"#,
        "quote-downgraded-server": #"^🎉 Congrats! You've been nerfed! You asked for (\S+); the server's own response says (\S+) answered\. No notice, no refund, no shame\.$"#,
        "quote-suspicious-server": #"^Odd: the server's own response says (\S+) answered your (\S+) request, while the fingerprint of the answers says (\S+) \((\d+%)\)\. Watching\.$"#,
        "quote-suspicious-server-only": #"^Hmm\. The server's own response says (\S+) answered your (\S+) request, and the fingerprint could not check it\. Watching\.$"#,
        "quote-upgraded": #"^🎉 Congrats, and this time we mean it: you've been upgraded\. Codex's own records say so: (.+?)\. Enjoy it while it lasts\.$"#,
        "quote-match-a": #"^All clear: the fingerprint says (\S+) \((\d+%)\), which is what you asked for\. The model you're paying for actually showed up\. Cherish it\.$"#,
        "quote-match-b": #"^No downgrade detected: (\S+) at (\d+%)\. Suspiciously honest\. I'll keep watching\.$"#,
        "quote-suspicious": #"^Hmm\. The fingerprint leans (\S+) \((\d+%)\) over your (\S+) \((\d+%)\), but not confidently enough to call it\. I asked again and it is still murky\. Watching\.$"#,
        "quote-unlisted": #"^(\S+) isn't in the fingerprint bank yet, so I can only tell you who it looks like: (\S+) \((\d+%)\)\. Not a verdict\.$"#,
        "quote-invalid": #"^Couldn't get a usable sample: (.+)\. No verdict, no congratulations\.$"#,
        "quote-settings-downgrade": #"^Heads up: (.+?)\. If that wasn't you clicking, congrats — you've been downgraded!$"#,
        "quote-nudge": #"^Probe due \((.+?)\)\. Say  (.+?)  in this session, or  (.+?)  to keep it out of your context\.$"#,
        "probe-due-turns": #"^(\d+) turns since the last probe$"#,
        "probe-due-minutes": #"^(\d+) min elapsed$"#,
        "quote-unknown-model": #"^No expected model recorded for this session; the fingerprint says (\S+) \((\d+%)\)\.$"#,
        "evidence-raw-hidden-model": #"^hidden/internal model (\S+) ran a turn$"#,
        "evidence-raw-applied-model": #"^thread settings switched model (\S+) → (\S+) \((upgrade|downgrade|lateral)\)$"#,
        "evidence-raw-silent-model": #"^model (\S+) → (\S+) with no settings change \((upgrade|downgrade|lateral)\)$"#,
        "evidence-raw-applied-effort": #"^thread settings switched reasoning effort (\S+) → (\S+)$"#,
        "evidence-raw-silent-effort": #"^reasoning effort (\S+) → (\S+) with no settings change$"#,
        "evidence-raw-tier": #"^service tier (\S+) → (\S+)$"#,
        "evidence-raw-context": #"^model context window (\S+) → (\S+)$"#,
        "evidence-compact-upgraded-settings": #"^Upgraded: (\S+) → (\S+) · via settings$"#,
        "evidence-compact-upgraded": #"^Upgraded: (\S+) → (\S+)$"#,
        "evidence-compact-silent-model": #"^Silent model change: (\S+) → (\S+)$"#,
        "evidence-compact-limit-model": #"^Codex switched model (\S+) → (\S+) at the usage limit \((\d+%)\)$"#,
        "evidence-compact-settings-model": #"^Settings: model (\S+) → (\S+) · was that you\?$"#,
        "evidence-compact-silent-effort": #"^Silent effort change: (\S+) → (\S+)$"#,
        "evidence-compact-limit-effort": #"^Codex switched effort (\S+) → (\S+) at the usage limit \((\d+%)\)$"#,
        "evidence-compact-settings-effort": #"^Settings: effort (\S+) → (\S+) · was that you\?$"#,
        "evidence-compact-hidden": #"^Hidden model ran: (\S+)$"#,
        "evidence-compact-context": #"^Context window (\S+) → (\S+)$"#,
        "evidence-compact-tier": #"^Tier (\S+) → (\S+)$"#,
        "report-last-probe": #"^Last probe · (.+)$"#,
        "report-earlier": #"^Earlier · (.+)$"#,
        "report-last-attempt": #"^Last attempt · (.+)$"#,
        "report-fingerprint": #"^Fingerprint · (.*)$"#,
        "report-evidence": #"^Evidence · (.+)$"#,
        "report-server": #"^Server · (.+)$"#,
        "report-server-part": #"^server: (\S+)$"#,
        "server-no-answer": #"^no answer: (.+)$"#,
        "server-as-asked": #"^(\S+), as asked$"#,
        "server-unrecognized": #"^(\S+), asked for (\S+) · unknown name, not counted$"#,
        "server-asked-for": #"^(\S+), asked for (\S+)$"#,
        "report-count": #"^(\d+) of (\d+) answers$"#,
        "report-rounds": #"^(\d+) rounds$"#,
        "report-retried-count": #"^retried (\d+)×$"#,
        "report-seconds": #"^(\d+(?:\.\d+)?) s$"#,
        "report-client": #"^as (.+)$"#,
        "report-probe-id": #"^probe (\S+)$"#,
        "report-declared": #"^(\S+) (\d+%), declared (\d+%)$"#,
        "report-prediction": #"^(\S+) (\d+%)$"#,
        "report-account-unknown": #"^(.+), account unknown$"#,
        "report-account-other": #"^(.+), another account$"#,
        "error-appserver-transport": #"^codex app-server transport closed: (.+)$"#,
        "error-appserver-exit": #"^codex app-server exited during (.+)$"#,
        "error-codex-timeout": #"^codex (\S+) timed out after (\d+)s$"#,
        "error-codex-method": #"^codex ([^:]+): (.+)$"#,
        "error-thread-field": #"^thread metadata lacks (\S+)$"#,
        "error-fork-model": #"^fork settings differ from the thread \((\S+) vs (\S+)\)$"#,
        "error-probe-tool": #"^probe attempted a tool \(([^()]*)\); no sample accepted$"#,
        "error-probe-turn-status": #"^probe turn ended with status (\S+)$"#,
        "error-probe-inference": #"^probe inference failed: (.+)$"#,
        "error-probe-request": #"^probe requested (.+); refused, no sample accepted$"#,
        "error-answer-count": #"^answer (\d+): only (\d+) valid integers$"#,
        "error-unexpected": #"^unexpected error: (.+)$"#,
        "error-cannot-start-python": #"^cannot start python3: (.+)$"#,
        "error-dgc-exit": #"^dgc exited with (.+)$"#,
        "update-failed": #"^failed: (.+)$"#,
        "update-http": #"^HTTP (\d{3})$"#,
        "update-version-not-newer": #"^(\S+) is not newer than (\S+)$"#,
        "update-download": #"^download: (.+)$"#,
        "update-checksum": #"^checksum: (.+)$"#,
        "update-extract": #"^extract: (.+)$"#,
        "update-info-plist": #"^Info\.plist: (.+)$"#,
        "update-archive-version": #"^the archive is version (\S+), the release says (\S+)$"#,
        "update-move-old": #"^cannot move the old app aside: (.+)$"#,
        "update-move-new": #"^cannot put the new app in place: (.+)$"#,
        "update-download-limit": #"^archive larger than 300 MB$"#,
        "update-checksum-mismatch": #"^sha256 mismatch: the archive is not the one the release lists$"#,
        "update-no-app": #"^no \.app inside the archive$"#
    ].mapValues { try! NSRegularExpression(pattern: $0) }

    private static let backendExactKeys: [String: String] = [
        "account hidden": "backend.account.hidden",
        "no usable sample": "backend.no-usable-sample",
        "no usable answer": "backend.no-usable-answer",
        "waiting for the current turn to finish": "backend.waiting-turn",
        "Probing, ephemeral forks in flight…": "backend.probing-forks",
        "No probe yet": "backend.report.no-probe",
        "Earlier": "backend.report.earlier",
        "Last probe": "backend.report.last-probe",
        "Last attempt": "backend.report.last-attempt",
        "Fingerprint": "backend.report.fingerprint",
        "Evidence": "backend.report.evidence",
        "reverted": "backend.report.reverted",
        "Failed": "backend.verdict.failed",
        "Downgraded": "backend.verdict.downgraded",
        "Downgrade": "backend.verdict.downgrade",
        "Upgrade": "backend.verdict.upgrade",
        "Rerouted": "backend.verdict.rerouted",
        "Suspicious": "backend.verdict.suspicious",
        "Match": "backend.verdict.match",
        "Unlisted": "backend.verdict.unlisted",
        "Invalid": "backend.verdict.invalid",
        "Unverified": "backend.verdict.unverified",
        "no release archive found": "backend.update.no-archive",
        "cannot find the installed IsGPTNerfed.app": "backend.update.app-not-found",
        "archive larger than 300 MB": "backend.update.too-large",
        "sha256 mismatch: the archive is not the one the release lists": "backend.update.checksum-mismatch",
        "no .app inside the archive": "backend.update.no-app",
        "no valid ChatGPT access token (API-key login, signed out, or expired)": "backend.server.no-token",
        "the stream ended before response.created": "backend.server.stream-ended"
    ]

    /// Translate only app-owned backend templates. Unknown strings and variable data pass through unchanged.
    static func backend(_ text: String, language: String? = nil) -> String {
        guard !text.isEmpty else { return text }
        // English and unsupported-language fallback preserves backend formatting verbatim.
        guard usesSimplifiedChinese(language: language) else { return text }
        if text.contains("\n") {
            let lines = text.components(separatedBy: "\n")
            let isReport = lines.first?.hasPrefix("is-gpt-nerfed · ") == true
            return lines.enumerated().map { index, line in
                isReport && index == 0 ? line : backendLine(line, language: language)
            }.joined(separator: "\n")
        }
        return backendLine(text, language: language)
    }

    private static func backendLine(_ text: String, language: String?) -> String {
        if let key = backendExactKeys[text] { return backendFormat(key, language: language) }
        if let groups = backendMatch("session-title", text) {
            return backendFormat("backend.title.session", arguments: [groups[0]], language: language)
        }

        if let result = translateQuote(text, language: language) { return result }
        if let result = translateEvidence(text, language: language) { return result }
        if let result = translateReportLine(text, language: language) { return result }
        if let result = translateError(text, language: language) { return result }
        if let result = translateUpdate(text, language: language) { return result }

        if let key = demoTitleKey(text) { return backendFormat(key, language: language) }
        return text
    }

    private static func demoTitleKey(_ text: String) -> String? {
        switch text {
        case "Refactor payment webhooks": return "backend.title.demo.payment-webhooks"
        case "Investigate flaky CI on main": return "backend.title.demo.flaky-ci"
        case "Add OAuth device flow": return "backend.title.demo.oauth-device-flow"
        case "Rewrite the docs site": return "backend.title.demo.docs-site"
        case "Migrate to Postgres 17": return "backend.title.demo.postgres"
        case "Write release notes v2.3": return "backend.title.demo.release-notes"
        default: return nil
        }
    }

    private static func translateQuote(_ text: String, language: String?) -> String? {
        if let c = backendMatch("quote-mismatch-downgrade-a", text) {
            return backendFormat("backend.quote.mismatch-downgrade-a", arguments: c, language: language)
        }
        if let c = backendMatch("quote-mismatch-downgrade-b", text) {
            return backendFormat("backend.quote.mismatch-downgrade-b", arguments: c, language: language)
        }
        if let c = backendMatch("quote-mismatch-upgrade", text) {
            return backendFormat("backend.quote.mismatch-upgrade", arguments: c, language: language)
        }
        if let c = backendMatch("quote-mismatch-lateral", text) {
            return backendFormat("backend.quote.mismatch-lateral", arguments: c, language: language)
        }
        if let c = backendMatch("quote-downgraded-hard", text) {
            return backendFormat("backend.quote.downgraded-hard", arguments: [backendLine(c[0], language: language)], language: language)
        }
        if let c = backendMatch("quote-downgraded-server", text) {
            return backendFormat("backend.quote.downgraded-server", arguments: c, language: language)
        }
        if let c = backendMatch("quote-suspicious-server", text) {
            return backendFormat("backend.quote.suspicious-server", arguments: c, language: language)
        }
        if let c = backendMatch("quote-suspicious-server-only", text) {
            return backendFormat("backend.quote.suspicious-server-only", arguments: c, language: language)
        }
        if let c = backendMatch("quote-upgraded", text) {
            return backendFormat("backend.quote.upgraded", arguments: [backendLine(c[0], language: language)], language: language)
        }
        if let c = backendMatch("quote-match-a", text) {
            return backendFormat("backend.quote.match-a", arguments: c, language: language)
        }
        if let c = backendMatch("quote-match-b", text) {
            return backendFormat("backend.quote.match-b", arguments: c, language: language)
        }
        if let c = backendMatch("quote-suspicious", text) {
            return backendFormat("backend.quote.suspicious", arguments: c, language: language)
        }
        if let c = backendMatch("quote-unlisted", text) {
            return backendFormat("backend.quote.unlisted", arguments: c, language: language)
        }
        if let c = backendMatch("quote-invalid", text) {
            return backendFormat("backend.quote.invalid", arguments: [backendLine(c[0], language: language)], language: language)
        }
        if let c = backendMatch("quote-settings-downgrade", text) {
            return backendFormat("backend.quote.settings-downgrade", arguments: [backendLine(c[0], language: language)], language: language)
        }
        if let c = backendMatch("quote-nudge", text) {
            return backendFormat(
                "backend.quote.nudge",
                arguments: [translateProbeDueReason(c[0], language: language) ?? c[0], c[1], c[2]],
                language: language
            )
        }
        if let c = backendMatch("quote-unknown-model", text) {
            return backendFormat("backend.quote.unknown-model", arguments: c, language: language)
        }
        return nil
    }

    private static func translateProbeDueReason(_ value: String, language: String?) -> String? {
        switch value {
        case "requested": return backendFormat("backend.quote.nudge.why-requested", language: language)
        case "account changed since the last probe":
            return backendFormat("backend.quote.nudge.why-account-changed", language: language)
        default: break
        }
        if let c = backendMatch("probe-due-turns", value) {
            return backendFormat("backend.quote.nudge.why-turns", arguments: c, language: language)
        }
        if let c = backendMatch("probe-due-minutes", value) {
            return backendFormat("backend.quote.nudge.why-minutes", arguments: c, language: language)
        }
        return nil
    }

    private static func translateEvidence(_ text: String, language: String?) -> String? {
        if let c = backendMatch("evidence-raw-hidden-model", text) {
            return backendFormat("backend.evidence.raw.hidden-model", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-raw-applied-model", text) {
            return backendFormat("backend.evidence.raw.applied-model", arguments: [c[0], c[1], translatedDirection(c[2], language: language)], language: language)
        }
        if let c = backendMatch("evidence-raw-silent-model", text) {
            return backendFormat("backend.evidence.raw.silent-model", arguments: [c[0], c[1], translatedDirection(c[2], language: language)], language: language)
        }
        if let c = backendMatch("evidence-raw-applied-effort", text) {
            return backendFormat("backend.evidence.raw.applied-effort", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-raw-silent-effort", text) {
            return backendFormat("backend.evidence.raw.silent-effort", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-raw-tier", text) {
            return backendFormat("backend.evidence.raw.tier", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-raw-context", text) {
            return backendFormat("backend.evidence.raw.context", arguments: c, language: language)
        }

        if let c = backendMatch("evidence-compact-upgraded-settings", text) {
            return backendFormat("backend.evidence.compact.upgraded-settings", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-upgraded", text) {
            return backendFormat("backend.evidence.compact.upgraded", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-silent-model", text) {
            return backendFormat("backend.evidence.compact.silent-model", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-limit-model", text) {
            return backendFormat("backend.evidence.compact.limit-model", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-settings-model", text) {
            return backendFormat("backend.evidence.compact.settings-model", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-silent-effort", text) {
            return backendFormat("backend.evidence.compact.silent-effort", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-limit-effort", text) {
            return backendFormat("backend.evidence.compact.limit-effort", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-settings-effort", text) {
            return backendFormat("backend.evidence.compact.settings-effort", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-hidden", text) {
            return backendFormat("backend.evidence.compact.hidden-model", arguments: c, language: language)
        }
        if text == "Hidden model ran a turn" {
            return backendFormat("backend.evidence.compact.hidden-model-turn", language: language)
        }
        if let c = backendMatch("evidence-compact-context", text) {
            return backendFormat("backend.evidence.compact.context", arguments: c, language: language)
        }
        if let c = backendMatch("evidence-compact-tier", text) {
            return backendFormat("backend.evidence.compact.tier", arguments: c, language: language)
        }
        return nil
    }

    private static func translateReportLine(_ text: String, language: String?) -> String? {
        if let c = backendMatch("report-last-probe", text) {
            return backendFormat("backend.report.last-probe", language: language) + " · " + translateProbeLine(c[0], language: language)
        }
        if let c = backendMatch("report-earlier", text) {
            return backendFormat("backend.report.earlier", language: language) + " · " + translateProbeLine(c[0], language: language)
        }
        if let c = backendMatch("report-last-attempt", text) {
            return backendFormat("backend.report.last-attempt", language: language) + " · " + translateProbeLine(c[0], language: language)
        }
        if let c = backendMatch("report-fingerprint", text) {
            return backendFormat("backend.report.fingerprint", language: language) + " · " + c[0]
        }
        if let c = backendMatch("report-evidence", text) {
            return translateReportEvidence(c[0], language: language)
        }
        if let c = backendMatch("report-server", text) {
            return backendFormat("backend.report.server", language: language) + " · " + translateServerValue(c[0], language: language)
        }
        return nil
    }

    /// The report's Server line: "gpt-6-astra, as asked" · "gpt-5.6-luna, asked for gpt-6-astra" · "no answer: …".
    private static func translateServerValue(_ value: String, language: String?) -> String {
        if let c = backendMatch("server-no-answer", value) {
            return backendFormat("backend.server.no-answer", arguments: [backendLine(c[0], language: language)], language: language)
        }
        if let c = backendMatch("server-as-asked", value) {
            return backendFormat("backend.server.as-asked", arguments: c, language: language)
        }
        if let c = backendMatch("server-unrecognized", value) {
            return backendFormat("backend.server.unrecognized", arguments: c, language: language)
        }
        if let c = backendMatch("server-asked-for", value) {
            return backendFormat("backend.server.asked-for", arguments: c, language: language)
        }
        return value
    }

    private static func translateProbeLine(_ text: String, language: String?) -> String {
        let parts = text.components(separatedBy: " · ")
        guard let first = parts.first, let translatedVerdict = verdict(first, language: language) else { return text }
        var output = [translatedVerdict]
        for part in parts.dropFirst() {
            if let c = backendMatch("report-account-unknown", part), let label = verdict(c[0], language: language) {
                output.append(backendFormat("backend.report.account-unknown", arguments: [label], language: language))
            } else if let c = backendMatch("report-account-other", part), let label = verdict(c[0], language: language) {
                output.append(backendFormat("backend.report.account-other", arguments: [label], language: language))
            } else if let c = backendMatch("report-count", part) {
                output.append(backendFormat("backend.report.count", arguments: c, language: language))
            } else if part == "retried once" {
                output.append(backendFormat("backend.report.retried-once", language: language))
            } else if let c = backendMatch("report-retried-count", part) {
                output.append(backendFormat("backend.report.retried-count", arguments: c, language: language))
            } else if let c = backendMatch("report-rounds", part) {
                output.append(backendFormat("backend.report.rounds", arguments: c, language: language))
            } else if let c = backendMatch("report-seconds", part) {
                output.append(backendFormat("backend.report.seconds", arguments: c, language: language))
            } else if let c = backendMatch("report-client", part) {
                output.append(backendFormat("backend.report.client", arguments: c, language: language))
            } else if let c = backendMatch("report-probe-id", part) {
                output.append(backendFormat("backend.report.probe-id", arguments: c, language: language))
            } else if let c = backendMatch("report-server-part", part) {
                output.append(backendFormat("backend.report.server-part", arguments: c, language: language))
            } else if let c = backendMatch("report-declared", part) {
                output.append(backendFormat("backend.report.prediction-declared", arguments: c, language: language))
            } else if let c = backendMatch("report-prediction", part) {
                output.append(c[0] + " " + c[1])
            } else if let age = translatedAge(part, language: language) {
                output.append(age)
            } else {
                output.append(backendLine(part, language: language))
            }
        }
        return output.joined(separator: " · ")
    }

    private static func translateReportEvidence(_ value: String, language: String?) -> String {
        var remainder = value
        var reverted = false
        if remainder.hasSuffix(" · reverted") {
            remainder.removeLast(" · reverted".count)
            reverted = true
        }
        var age: String?
        let parts = remainder.components(separatedBy: " · ")
        if let last = parts.last, let translated = translatedAge(last, language: language) {
            age = translated
            remainder = parts.dropLast().joined(separator: " · ")
        }
        var result = backendFormat("backend.report.evidence", language: language) + " · " + backendLine(remainder, language: language)
        if let age { result += " · " + age }
        if reverted { result += " · " + backendFormat("backend.report.reverted", language: language) }
        return result
    }

    private static func verdict(_ value: String, language: String?) -> String? {
        backendExactKeys[value].map { backendFormat($0, language: language) }
    }

    private static func translatedDirection(_ value: String, language: String?) -> String {
        switch value {
        case "upgrade": return backendFormat("backend.direction.upgrade", language: language)
        case "downgrade": return backendFormat("backend.direction.downgrade", language: language)
        case "lateral": return backendFormat("backend.direction.lateral", language: language)
        default: return value
        }
    }

    private static func translatedAge(_ value: String, language: String?) -> String? {
        let pattern = #"^(\d+)([smhd]) ago$"#
        guard let groups = match(pattern: pattern, text: value) else { return nil }
        let unitKey: String
        switch groups[1] {
        case "s": unitKey = "backend.report.seconds-ago"
        case "m": unitKey = "backend.report.minutes-ago"
        case "h": unitKey = "backend.report.hours-ago"
        case "d": unitKey = "backend.report.days-ago"
        default: return nil
        }
        return backendFormat(unitKey, arguments: [groups[0]], language: language)
    }

    private static func translateError(_ text: String, language: String?) -> String? {
        switch text {
        case "thread is busy": return backendFormat("backend.error.thread-busy", language: language)
        case "session has no finished turn yet": return backendFormat("backend.error.no-finished-turn", language: language)
        case "session has no finished turn yet; wait for the current turn to finish":
            return backendFormat("backend.error.wait-finished-turn", language: language)
        case "codex returned metadata for a different thread": return backendFormat("backend.error.wrong-thread", language: language)
        case "session has no persisted history to fork (ephemeral or not saved yet)":
            return backendFormat("backend.error.no-persisted-history", language: language)
        case "fork reasoning effort differs from the thread": return backendFormat("backend.error.fork-effort-differs", language: language)
        case "codex did not create an ephemeral fork of the target thread": return backendFormat("backend.error.fork-not-ephemeral", language: language)
        case "probe did not return a final text answer": return backendFormat("backend.error.no-final-answer", language: language)
        default: break
        }
        if let c = backendMatch("error-appserver-transport", text) {
            return backendFormat("backend.error.appserver-transport", arguments: c, language: language)
        }
        if let c = backendMatch("error-appserver-exit", text) {
            return backendFormat("backend.error.appserver-exit", arguments: c, language: language)
        }
        if let c = backendMatch("error-codex-timeout", text) {
            return backendFormat("backend.error.codex-timeout", arguments: c, language: language)
        }
        if let c = backendMatch("error-codex-method", text) {
            return backendFormat("backend.error.codex-method", arguments: [c[0], backendLine(c[1], language: language)], language: language)
        }
        if let c = backendMatch("error-thread-field", text) {
            return backendFormat("backend.error.thread-field", arguments: c, language: language)
        }
        if let c = backendMatch("error-fork-model", text) {
            return backendFormat("backend.error.fork-model", arguments: c, language: language)
        }
        if let c = backendMatch("error-probe-tool", text) {
            return backendFormat("backend.error.probe-tool", arguments: c, language: language)
        }
        if let c = backendMatch("error-probe-turn-status", text) {
            return backendFormat("backend.error.probe-turn-status", arguments: c, language: language)
        }
        if let c = backendMatch("error-probe-inference", text) {
            return backendFormat("backend.error.probe-inference", arguments: [backendLine(c[0], language: language)], language: language)
        }
        if let c = backendMatch("error-probe-request", text) {
            return backendFormat("backend.error.probe-request", arguments: c, language: language)
        }
        if let c = backendMatch("error-answer-count", text) {
            return backendFormat("backend.error.answer-count", arguments: c, language: language)
        }
        if let c = backendMatch("error-unexpected", text) {
            return backendFormat("backend.error.unexpected", arguments: [backendLine(c[0], language: language)], language: language)
        }
        if let c = backendMatch("error-cannot-start-python", text) {
            return backendFormat("backend.error.cannot-start-python", arguments: c, language: language)
        }
        if let c = backendMatch("error-dgc-exit", text) {
            return backendFormat("backend.error.dgc-exit", arguments: c, language: language)
        }
        return nil
    }

    private static func translateUpdate(_ text: String, language: String?) -> String? {
        if text == "downloading" { return backendFormat("backend.update.downloading", language: language) }
        if text == "installed" { return backendFormat("backend.update.installed", language: language) }
        if let c = backendMatch("update-failed", text) {
            return backendFormat("backend.update.failed", arguments: [translateUpdateReason(c[0], language: language) ?? c[0]], language: language)
        }
        return translateUpdateReason(text, language: language)
    }

    private static func translateUpdateReason(_ text: String, language: String?) -> String? {
        if let c = backendMatch("update-http", text) {
            return backendFormat("backend.update.http", arguments: c, language: language)
        }
        if text == "no release archive found" { return backendFormat("backend.update.no-archive", language: language) }
        if text == "cannot find the installed IsGPTNerfed.app" { return backendFormat("backend.update.app-not-found", language: language) }
        if text == "archive larger than 300 MB" { return backendFormat("backend.update.too-large", language: language) }
        if text == "sha256 mismatch: the archive is not the one the release lists" {
            return backendFormat("backend.update.checksum-mismatch", language: language)
        }
        if text == "no .app inside the archive" { return backendFormat("backend.update.no-app", language: language) }
        if let c = backendMatch("update-version-not-newer", text) {
            return backendFormat("backend.update.version-not-newer", arguments: c, language: language)
        }
        if let c = backendMatch("update-download", text) {
            return backendFormat("backend.update.download", arguments: c, language: language)
        }
        if let c = backendMatch("update-checksum", text) {
            return backendFormat("backend.update.checksum", arguments: c, language: language)
        }
        if let c = backendMatch("update-extract", text) {
            return backendFormat("backend.update.extract", arguments: c, language: language)
        }
        if let c = backendMatch("update-info-plist", text) {
            return backendFormat("backend.update.info-plist", arguments: c, language: language)
        }
        if let c = backendMatch("update-archive-version", text) {
            return backendFormat("backend.update.archive-version", arguments: c, language: language)
        }
        if let c = backendMatch("update-move-old", text) {
            return backendFormat("backend.update.move-old", arguments: c, language: language)
        }
        if let c = backendMatch("update-move-new", text) {
            return backendFormat("backend.update.move-new", arguments: c, language: language)
        }
        return nil
    }

    private static func backendMatch(_ name: String, _ text: String) -> [String]? {
        guard let regex = backendPatterns[name] else { return nil }
        return match(regex: regex, text: text)
    }

    private static func match(pattern: String, text: String) -> [String]? {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        return match(regex: regex, text: text)
    }

    private static func match(regex: NSRegularExpression, text: String) -> [String]? {
        let range = NSRange(text.startIndex..., in: text)
        guard let result = regex.firstMatch(in: text, range: range), result.range == range else { return nil }
        return (1..<result.numberOfRanges).map { index in
            guard let range = Range(result.range(at: index), in: text) else { return "" }
            return String(text[range])
        }
    }

    private static func backendFormat(_ key: String, arguments: [String] = [], language: String?) -> String {
        let bundle = language.map { backendResourceBundle(for: $0) ?? backendEnglishBundle } ?? resources
        let translated = bundle.localizedString(forKey: key, value: key, table: "Backend")
        let format = translated == key
            ? backendEnglishBundle.localizedString(forKey: key, value: key, table: "Backend")
            : translated
        guard !arguments.isEmpty else { return format }
        let locale = Locale(identifier: bundle.preferredLocalizations.first ?? Locale.current.identifier)
        return String(format: format, locale: locale, arguments: arguments.map { $0 as CVarArg })
    }

    private static func backendResourceBundle(for language: String) -> Bundle? {
        resourceBundle(for: language)  // one case-insensitive lookup for both tables
    }

    private static func usesSimplifiedChinese(language: String?) -> Bool {
        // Localization identifiers come back lowercased from a SwiftPM resource bundle (zh-hans), so compare loosely.
        if let language { return language.lowercased() == "zh-hans" }
        return resources.preferredLocalizations.contains { $0.lowercased() == "zh-hans" }
    }
}
