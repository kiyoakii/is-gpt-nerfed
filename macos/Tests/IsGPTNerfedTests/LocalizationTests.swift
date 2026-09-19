import Foundation
import XCTest
@testable import IsGPTNerfed

final class LocalizationTests: XCTestCase {
    func testChineseTranslationsAndFormatArguments() {
        XCTAssertEqual(L10n.tr("Match", language: "zh-Hans"), "匹配")
        XCTAssertEqual(L10n.tr("%@ of %@ answers", language: "zh-Hans", arguments: ["2", "3"]), "可用回答 2 / 3")
        XCTAssertEqual(L10n.tr("declared %@", language: "zh-Hans", arguments: ["91%"]), "所选模型 91%")
        XCTAssertEqual(L10n.frequency("turns:6", active: true, language: "zh-Hans"), "每 6 轮")
        XCTAssertEqual(L10n.frequency("45m", active: true, language: "zh-Hans"), "每使用 45 分钟")
        XCTAssertEqual(L10n.frequency("3h", active: false, language: "zh-Hans"), "每 3 小时")
        XCTAssertEqual(L10n.sessionTitle("Session 4", isDemo: false, isHidden: true, language: "zh-Hans"), "会话 4")
        XCTAssertEqual(L10n.tr("account hidden", language: "zh-Hans"), "账户已隐藏")
    }

    func testEnglishFallbackForUnsupportedLanguageAndUnknownKey() {
        XCTAssertEqual(L10n.tr("Match", language: "fr"), "Match")
        XCTAssertEqual(L10n.tr("Unknown future label", language: "fr"), "Unknown future label")
    }

    func testDynamicStatusCountsAndUnknownStatusFallback() {
        XCTAssertEqual(
            L10n.statusMessage("2 downgraded · 1 suspicious · 3 probes running", language: "zh-Hans"),
            "2 个会话降配 · 1 个可疑 · 3 个正在检测"
        )
        XCTAssertEqual(L10n.statusMessage("1 probe running", language: "zh-Hans"), "1 个正在检测")
        XCTAssertEqual(L10n.statusMessage("all clear", language: "fr"), "All clear")
        XCTAssertEqual(L10n.statusMessage("2 downgraded · future state", language: "zh-Hans"), "2 downgraded · future state")
    }

    func testDynamicAgoAndRawEvidenceBoundary() {
        XCTAssertEqual(L10n.localizedAgo("59s ago", language: "zh-Hans"), "59 秒前")
        XCTAssertEqual(L10n.localizedAgo("12m ago", language: "zh-Hans"), "12 分钟前")
        XCTAssertEqual(L10n.localizedAgo("3h ago", language: "zh-Hans"), "3 小时前")
        XCTAssertEqual(L10n.localizedAgo("2d ago", language: "zh-Hans"), "2 天前")
        XCTAssertEqual(L10n.localizedAgo("waiting for a new state", language: "zh-Hans"), "waiting for a new state")

        let evidence = "Silent model change: gpt-6-astra → gpt-reserve"
        XCTAssertEqual(
            L10n.evidenceText(evidence, ago: "2m ago", active: false, language: "zh-Hans"),
            "模型已悄悄切换：gpt-6-astra → gpt-reserve · 2 分钟前 · 已还原"
        )
        XCTAssertEqual(evidence, "Silent model change: gpt-6-astra → gpt-reserve", "translation must not mutate stored evidence")
    }

    func testBackendTranslatesEveryScannerEvidenceKindAndPreservesEffortValues() {
        let examples: [(String, String)] = [
            ("hidden/internal model gpt-reserve ran a turn", "隐藏或内部模型 gpt-reserve 运行了一轮"),
            ("thread settings switched model gpt-5.6-sol → gpt-6-sol (upgrade)", "会话设置将模型从 gpt-5.6-sol 切换为 gpt-6-sol（升配）"),
            ("model gpt-6-astra → gpt-reserve with no settings change (downgrade)", "模型在未更改设置的情况下从 gpt-6-astra 切换为 gpt-reserve（降配）"),
            ("thread settings switched model gpt-6-astra → gpt-6-sol (lateral)", "会话设置将模型从 gpt-6-astra 切换为 gpt-6-sol（同级切换）"),
            ("thread settings switched reasoning effort xhigh → medium", "会话设置将推理级别从 xhigh 调整为 medium"),
            ("reasoning effort high → low with no settings change", "推理级别在未更改设置的情况下从 high 调整为 low"),
            ("service tier default → flex", "服务等级从 default 调整为 flex"),
            ("model context window 272000 → 128000", "模型上下文窗口从 272000 变为 128000"),
            ("Upgraded: gpt-5.6-sol → gpt-6-sol · via settings", "已升配：gpt-5.6-sol → gpt-6-sol · 在设置中修改"),
            ("Codex switched model gpt-6-astra → gpt-5.6-luna at the usage limit (98%)", "Codex 在用量达到上限时将模型从 gpt-6-astra 切换为 gpt-5.6-luna（98%）"),
            ("Settings: model gpt-6-astra → gpt-5.6-luna · was that you?", "设置变更：模型 gpt-6-astra → gpt-5.6-luna · 是你改的吗？"),
            ("Silent effort change: xhigh → medium", "推理级别已悄悄调整：xhigh → medium"),
            ("Codex switched effort xhigh → medium at the usage limit (98%)", "Codex 在用量达到上限时将推理级别从 xhigh 调整为 medium（98%）"),
            ("Settings: effort xhigh → medium · was that you?", "设置变更：推理级别 xhigh → medium · 是你改的吗？"),
            ("Hidden model ran: gpt-reserve", "检测到隐藏模型运行：gpt-reserve"),
            ("Hidden model ran a turn", "检测到隐藏模型运行了一轮"),
            ("Context window 272k → 128k", "上下文窗口：272k → 128k"),
            ("Tier default → flex", "服务等级：default → flex")
        ]
        for (source, expected) in examples {
            XCTAssertEqual(L10n.backend(source, language: "zh-Hans"), expected, source)
        }

        for value in ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"] {
            XCTAssertEqual(L10n.backend(value, language: "zh-Hans"), value)
        }
    }

    func testBackendTranslatesProbeQuotesNotesAndNestedErrors() {
        let quotes = [
            "🎉 Congrats! You've been nerfed! You asked for gpt-6-astra; the fingerprint says gpt-5.6-luna (91%, 3/3 answers). Enjoy the discount you didn't ask for.",
            "Great news: your gpt-6-astra session is answering like gpt-5.6-luna (91%). Nobody told you, but somebody saved money. Congrats!",
            "Congrats! You've been secretly upgraded: you asked for gpt-5.6-sol, the fingerprint says gpt-6-sol (99%). Don't tell anyone.",
            "Congrats! You've been… re-routed. You asked for gpt-6-astra, the fingerprint says gpt-6-sol (88%). Same tier, different brain.",
            "🎉 Congrats! You've been nerfed! Codex's own records say so: hidden/internal model gpt-reserve ran a turn. No notice, no refund, no shame.",
            "🎉 Congrats, and this time we mean it: you've been upgraded. Codex's own records say so: Upgraded: gpt-5.6-sol → gpt-6-sol · via settings. Enjoy it while it lasts.",
            "All clear: the fingerprint says gpt-6-astra (100%), which is what you asked for. The model you're paying for actually showed up. Cherish it.",
            "No downgrade detected: gpt-6-astra at 99%. Suspiciously honest. I'll keep watching.",
            "Hmm. The fingerprint leans gpt-5.6-luna (62%) over your gpt-6-astra (31%), but not confidently enough to call it. I asked again and it is still murky. Watching.",
            "gpt-6-astra isn't in the fingerprint bank yet, so I can only tell you who it looks like: gpt-5.6-luna (90%). Not a verdict.",
            "Couldn't get a usable sample: no usable answer. No verdict, no congratulations.",
            "Heads up: model gpt-6-astra → gpt-reserve with no settings change (downgrade). If that wasn't you clicking, congrats — you've been downgraded!",
            "Probe due (8 turns since the last probe). Say  $is-gpt-nerfed  in this session, or  nerfed probe now --side  to keep it out of your context.",
            "No expected model recorded for this session; the fingerprint says gpt-5.6-luna (91%)."
        ]
        for quote in quotes {
            let translated = L10n.backend(quote, language: "zh-Hans")
            XCTAssertNotEqual(translated, quote, quote)
            XCTAssertFalse(translated.contains("Congrats"), translated)
        }
        XCTAssertEqual(
            L10n.backend(
                "Probe due (8 turns since the last probe). Say  $is-gpt-nerfed  in this session, or  nerfed probe now --side  to keep it out of your context.",
                language: "zh-Hans"
            ),
            "检测已到时间（距离上次检测已有 8 轮）。在当前会话中输入 $is-gpt-nerfed，或使用 nerfed probe now --side，避免把检测内容带入当前上下文。"
        )
        XCTAssertEqual(
            L10n.backend("Probe due (15 min elapsed). Say  $is-gpt-nerfed  in this session, or  nerfed probe now --side  to keep it out of your context.", language: "zh-Hans"),
            "检测已到时间（已过去 15 分钟）。在当前会话中输入 $is-gpt-nerfed，或使用 nerfed probe now --side，避免把检测内容带入当前上下文。"
        )
        XCTAssertEqual(
            L10n.backend("Probe due (requested). Say  $is-gpt-nerfed  in this session, or  nerfed probe now --side  to keep it out of your context.", language: "zh-Hans"),
            "检测已到时间（手动请求）。在当前会话中输入 $is-gpt-nerfed，或使用 nerfed probe now --side，避免把检测内容带入当前上下文。"
        )
        XCTAssertEqual(
            L10n.backend("Probe due (account changed since the last probe). Say  $is-gpt-nerfed  in this session, or  nerfed probe now --side  to keep it out of your context.", language: "zh-Hans"),
            "检测已到时间（账户自上次检测后发生变化）。在当前会话中输入 $is-gpt-nerfed，或使用 nerfed probe now --side，避免把检测内容带入当前上下文。"
        )
        XCTAssertEqual(
            L10n.backend("Probe due (future reason). Say  $is-gpt-nerfed  in this session, or  nerfed probe now --side  to keep it out of your context.", language: "zh-Hans"),
            "检测已到时间（future reason）。在当前会话中输入 $is-gpt-nerfed，或使用 nerfed probe now --side，避免把检测内容带入当前上下文。"
        )

        XCTAssertEqual(L10n.backend("waiting for the current turn to finish", language: "zh-Hans"), "等待当前轮次结束")
        XCTAssertEqual(L10n.backend("thread is busy", language: "zh-Hans"), "当前会话仍在运行，请稍后重试。")
        XCTAssertEqual(
            L10n.backend("probe inference failed: probe attempted a tool (commandExecution); no sample accepted", language: "zh-Hans"),
            "模型检测失败：检测尝试调用工具（commandExecution），未接受任何样本。"
        )
        XCTAssertEqual(
            L10n.backend("failed: HTTP 404", language: "zh-Hans"),
            "更新失败：GitHub 请求失败（HTTP 404）"
        )
        XCTAssertEqual(
            L10n.backend("failed: download: connection reset by peer", language: "zh-Hans"),
            "更新失败：下载失败：connection reset by peer"
        )
        XCTAssertEqual(L10n.backend("future external failure", language: "zh-Hans"), "future external failure")
    }

    func testBackendTranslatesTheServerCheck() {
        let zh = "zh-Hans"
        XCTAssertEqual(
            L10n.backend("🎉 Congrats! You've been nerfed! You asked for gpt-6-astra; the server's own response says gpt-5.6-luna answered. No notice, no refund, no shame.", language: zh),
            "🎉 恭喜，你被降配了！你选的是 gpt-6-astra，服务器自己的响应却说回答的是 gpt-5.6-luna。没有通知，没有退款，也不必觉得难堪。"
        )
        XCTAssertEqual(
            L10n.backend("Odd: the server's own response says gpt-5.6-luna answered your gpt-6-astra request, while the fingerprint of the answers says gpt-6-astra (97%). Watching.", language: zh),
            "奇怪：服务器自己的响应说是 gpt-5.6-luna 回答了你选的 gpt-6-astra，但这些回答的指纹结果是 gpt-6-astra（97%）。继续观察。"
        )
        XCTAssertEqual(
            L10n.backend("Hmm. The server's own response says gpt-6-sol answered your gpt-6-astra request, and the fingerprint could not check it. Watching.", language: zh),
            "服务器自己的响应说是 gpt-6-sol 回答了你选的 gpt-6-astra，指纹这次没能核对。继续观察。"
        )
        XCTAssertEqual(L10n.backend("Server · gpt-5.6-luna, asked for gpt-6-astra", language: zh), "服务器 · gpt-5.6-luna，所选为 gpt-6-astra")
        XCTAssertEqual(L10n.backend("Server · gpt-6-astra, as asked", language: zh), "服务器 · gpt-6-astra，与所选一致")
        XCTAssertEqual(L10n.backend("Server · astra-x, asked for gpt-6-astra · unknown name, not counted", language: zh),
                       "服务器 · astra-x，所选为 gpt-6-astra · 名称未知，不计入判定")
        XCTAssertEqual(L10n.backend("Server · no answer: no valid ChatGPT access token (API-key login, signed out, or expired)", language: zh),
                       "服务器 · 未回答：没有有效的 ChatGPT 访问令牌（API 密钥登录、已退出或已过期）")
        XCTAssertEqual(L10n.backend("Server · no answer: HTTP 401: denied", language: zh), "服务器 · 未回答：HTTP 401: denied", "external text stays as it is")
        XCTAssertEqual(
            L10n.backend("Last probe · Suspicious · server: gpt-5.6-luna · gpt-6-astra 97% · probe abc", language: zh),
            "最近一次检测 · 可疑 · 服务器：gpt-5.6-luna · gpt-6-astra 97% · 检测 abc"
        )
        XCTAssertEqual(L10n.tr("server: %@", language: zh, arguments: ["gpt-5.6-luna"]), "服务器：gpt-5.6-luna")
        XCTAssertEqual(L10n.tr("Also ask the server which model answered", language: zh), "同时询问服务器实际用的模型")
        XCTAssertEqual(L10n.backend("Server · gpt-5.6-luna, asked for gpt-6-astra", language: "fr"), "Server · gpt-5.6-luna, asked for gpt-6-astra")
    }

    func testBackendReportTranslationKeepsUserTitleAndUnknownStrings() {
        let title = "Silent model change: foo"
        let raw = """
        is-gpt-nerfed · \(title) · gpt-6-astra @ high
        Last probe · Match · gpt-6-astra 100% · 3 of 3 answers · 41 s · 5m ago · as Codex Desktop · probe abc123
        Fingerprint · gpt-6-astra 100% · gpt-5.6-luna 0%
        Evidence · Silent model change: gpt-6-astra → gpt-reserve · 5m ago · reverted
        """
        let displayTitle = L10n.sessionTitle(title, isDemo: false, isHidden: false, language: "zh-Hans")
        let translated = L10n.report(raw, title: title, displayTitle: displayTitle, language: "zh-Hans")
        XCTAssertTrue(translated.hasPrefix("is-gpt-nerfed · Silent model change: foo · gpt-6-astra @ high"), translated)
        XCTAssertTrue(translated.contains("最近一次检测 · 匹配 · gpt-6-astra 100% · 3 / 3 个回答 · 41 秒 · 5 分钟前 · 客户端：Codex Desktop · 检测 abc123"), translated)
        XCTAssertTrue(translated.contains("模型指纹 · gpt-6-astra 100% · gpt-5.6-luna 0%"), translated)
        XCTAssertTrue(translated.contains("证据 · 模型已悄悄切换：gpt-6-astra → gpt-reserve · 5 分钟前 · 已还原"), translated)

        XCTAssertEqual(L10n.sessionTitle("Refactor payment webhooks", isDemo: false, isHidden: false, language: "zh-Hans"), "Refactor payment webhooks")
        XCTAssertEqual(L10n.sessionTitle("Refactor payment webhooks", isDemo: true, isHidden: false, language: "zh-Hans"), "重构支付回调")
        XCTAssertEqual(L10n.backend("Refactor payment webhooks", language: "zh-Hans"), "重构支付回调")
    }

    func testBackendEnglishAndUnsupportedLocaleFallbackAreVerbatim() {
        let effortEvidence = "Settings: effort high → low · was that you?"
        let report = "Last probe · Match · gpt-6-astra 100% · 3 of 3 answers · 41 s · 5m ago · probe abc123"
        XCTAssertEqual(L10n.backend(effortEvidence, language: "en"), effortEvidence)
        XCTAssertEqual(L10n.backend(effortEvidence, language: "fr"), effortEvidence)
        XCTAssertEqual(L10n.backend(report, language: "fr"), report)
        XCTAssertEqual(L10n.backend("Unknown external text", language: "zh-Hans"), "Unknown external text")
    }
}
