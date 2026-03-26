<script lang="ts">
    import RunningSpinner from "$lib/components/RunningSpinner.svelte";
    import TestBuilder from "$lib/components/TestBuilder.svelte";
    import {
        fetchDemo,
        fetchLatestResults,
        flattenIssuesBySeverity,
        triggerTestRun,
        type IssuesBySeverity,
        type LatestResultsResponse,
        type ScanResultPayload,
    } from "../services/backend-service";
    import { onDestroy } from "svelte";

    let isLoading = $state(false);
    let jobId = $state<string | null>(null);
    let startedMessage = $state<string | null>(null);
    let errorMessage = $state<string | null>(null);
    let latest = $state<LatestResultsResponse | null>(null);
    let polling = $state(false);

    let pollTimer: ReturnType<typeof setInterval> | null = null;

    let scanResult = $derived(
        latest?.result && typeof latest.result === "object" ? (latest.result as ScanResultPayload) : null
    );

    let severityBuckets = $derived((scanResult?.issues_by_severity ?? null) as IssuesBySeverity | null);

    let severityCounts = $derived(
        severityBuckets
            ? {
                  critical: severityBuckets.critical?.length ?? 0,
                  high: severityBuckets.high?.length ?? 0,
                  medium: severityBuckets.medium?.length ?? 0,
                  low: severityBuckets.low?.length ?? 0,
              }
            : { critical: 0, high: 0, medium: 0, low: 0 }
    );

    let issuesList = $derived(flattenIssuesBySeverity(severityBuckets ?? undefined));

    function severityPillClass(bucket: keyof IssuesBySeverity): string {
        switch (bucket) {
            case "critical":
                return "bg-red-100 text-red-900 border-red-200";
            case "high":
                return "bg-orange-100 text-orange-900 border-orange-200";
            case "medium":
                return "bg-amber-100 text-amber-900 border-amber-200";
            case "low":
                return "bg-slate-100 text-slate-700 border-slate-200";
            default:
                return "bg-gray-100 text-gray-800 border-gray-200";
        }
    }

    function issueBorderClass(bucket: keyof IssuesBySeverity): string {
        switch (bucket) {
            case "critical":
                return "border-l-red-500";
            case "high":
                return "border-l-orange-500";
            case "medium":
                return "border-l-amber-500";
            case "low":
                return "border-l-slate-400";
            default:
                return "border-l-gray-300";
        }
    }

    function riskBadgeClass(level: ScanResultPayload["risk_level"]): string {
        switch (level) {
            case "HIGH RISK":
                return "bg-red-100 text-red-900 border-red-200";
            case "MEDIUM RISK":
                return "bg-amber-100 text-amber-900 border-amber-200";
            case "LOW RISK":
                return "bg-emerald-100 text-emerald-900 border-emerald-200";
            default:
                return "bg-gray-100 text-gray-800 border-gray-200";
        }
    }

    /**
     * This is a POC, we'll improve that later.
     */
    const generate = async ({ startUrl, scenario }: { startUrl: string; scenario: string }) => {
        void scenario;

        errorMessage = null;
        latest = null;
        startedMessage = null;
        jobId = null;
        isLoading = true;

        try {
            const res = await triggerTestRun(startUrl);
            jobId = res.job_id;
            startedMessage = res.message ?? "Scan started";
            polling = true;
            startPolling();
        } catch (e) {
            errorMessage = e instanceof Error ? e.message : String(e);
        } finally {
            isLoading = false;
        }
    };

    const runDemo = async () => {
        stopPolling();
        errorMessage = null;
        startedMessage = "Demo loaded";
        jobId = "demo";
        isLoading = true;
        try {
            const payload = await fetchDemo();
            latest = {
                job_id: "demo",
                status: "completed",
                started_at: null,
                completed_at: null,
                result: payload,
                error: null,
            };
        } catch (e) {
            errorMessage = e instanceof Error ? e.message : String(e);
        } finally {
            isLoading = false;
        }
    };

    const startPolling = () => {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(async () => {
            try {
                const res = await fetchLatestResults();
                latest = res;
                if (res.status === "completed" || res.status === "failed") {
                    stopPolling();
                }
            } catch (e) {
                errorMessage = e instanceof Error ? e.message : String(e);
                stopPolling();
            }
        }, 1500);
    };

    const stopPolling = () => {
        polling = false;
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    };

    onDestroy(() => stopPolling());
</script>

<div class="min-h-screen flex flex-col items-center bg-slate-50/80">
    <div class="w-full max-w-3xl px-6 py-10 space-y-6">
        <div class="flex items-start justify-between gap-3 flex-wrap">
            <div class="flex-1 min-w-[280px]">
                <TestBuilder onTriggerRun={generate} />
            </div>
            <button
                type="button"
                class="h-10 px-4 rounded-full border border-gray-200 bg-white text-sm font-medium text-gray-900 shadow-sm hover:bg-gray-50"
                on:click={runDemo}
            >
                Run Demo
            </button>
        </div>

        {#if isLoading}
            <div class="flex items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
                <RunningSpinner />
                <div class="text-sm text-gray-700">Starting scan…</div>
            </div>
        {/if}

        {#if startedMessage}
            <div class="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-green-900 shadow-sm">
                <div class="font-medium">{startedMessage}</div>
                {#if jobId}
                    <div class="mt-1 text-xs opacity-80">Job <span class="font-mono">{jobId}</span></div>
                {/if}
            </div>
        {/if}

        {#if polling}
            <div class="text-sm text-gray-600">Fetching latest results…</div>
        {/if}

        {#if errorMessage}
            <div class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-900 shadow-sm">
                <div class="font-medium">Error</div>
                <div class="mt-1 text-sm">{errorMessage}</div>
            </div>
        {/if}

        {#if latest}
            <section class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-5">
                <header class="flex flex-wrap items-center justify-between gap-2">
                    <h2 class="text-lg font-semibold text-gray-900">Results</h2>
                    <span
                        class="rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize text-gray-700 bg-gray-50 border-gray-200"
                    >
                        {latest.status}
                    </span>
                </header>

                {#if latest.error}
                    <div class="rounded-lg border border-red-100 bg-red-50/80 px-3 py-2 text-sm text-red-900">
                        {latest.error}
                    </div>
                {/if}

                {#if scanResult?.summary}
                    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
                        <div class="rounded-lg border border-gray-100 bg-slate-50/90 px-4 py-3">
                            <div class="text-xs font-medium uppercase tracking-wide text-gray-500">Pages scanned</div>
                            <div class="mt-1 text-2xl font-semibold tabular-nums text-gray-900">
                                {scanResult.summary.total_pages_scanned}
                            </div>
                        </div>
                        <div class="rounded-lg border border-gray-100 bg-slate-50/90 px-4 py-3">
                            <div class="text-xs font-medium uppercase tracking-wide text-gray-500">Actions run</div>
                            <div class="mt-1 text-2xl font-semibold tabular-nums text-gray-900">
                                {scanResult.summary.total_actions_run}
                            </div>
                        </div>
                        <div class="col-span-2 rounded-lg border border-gray-100 bg-slate-50/90 px-4 py-3 sm:col-span-1">
                            <div class="text-xs font-medium uppercase tracking-wide text-gray-500">Issues</div>
                            <div class="mt-1 text-2xl font-semibold tabular-nums text-gray-900">
                                {scanResult.summary.total_issues_found}
                            </div>
                        </div>
                    </div>
                {:else if latest.status === "started" || latest.status === "none"}
                    <p class="text-sm text-gray-600">Waiting for scan output…</p>
                {/if}

                {#if scanResult?.risk_score != null || scanResult?.risk_level}
                    <div class="rounded-lg border border-gray-100 bg-white px-4 py-3">
                        <div class="flex items-center justify-between gap-3 flex-wrap">
                            <div>
                                <div class="text-xs font-medium uppercase tracking-wide text-gray-500">Risk score</div>
                                <div class="mt-1 text-3xl font-semibold tabular-nums text-gray-900">
                                    {scanResult?.risk_score ?? 0}
                                </div>
                            </div>
                            <span
                                class="inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold {riskBadgeClass(
                                    scanResult?.risk_level
                                )}"
                            >
                                {scanResult?.risk_level ?? "—"}
                            </span>
                        </div>
                    </div>
                {/if}

                {#if severityBuckets}
                    <div>
                        <h3 class="mb-2 text-sm font-medium text-gray-800">By severity</h3>
                        <div class="flex flex-wrap gap-2">
                            <span
                                class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium {severityPillClass(
                                    'critical'
                                )}"
                            >
                                Critical <span class="tabular-nums">{severityCounts.critical}</span>
                            </span>
                            <span
                                class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium {severityPillClass(
                                    'high'
                                )}"
                            >
                                High <span class="tabular-nums">{severityCounts.high}</span>
                            </span>
                            <span
                                class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium {severityPillClass(
                                    'medium'
                                )}"
                            >
                                Medium <span class="tabular-nums">{severityCounts.medium}</span>
                            </span>
                            <span
                                class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium {severityPillClass(
                                    'low'
                                )}"
                            >
                                Low <span class="tabular-nums">{severityCounts.low}</span>
                            </span>
                        </div>
                    </div>
                {/if}

                {#if severityBuckets?.critical?.length}
                    <div>
                        <h3 class="mb-3 text-sm font-semibold text-gray-900">Critical issues</h3>
                        <ul class="space-y-2">
                            {#each severityBuckets.critical as issue, i (`crit-${i}-${issue.message ?? ""}`)}
                                <li class="rounded-lg border border-l-4 border-red-200 bg-red-50/60 px-3 py-2.5 text-sm border-l-red-500">
                                    <div class="flex flex-wrap items-center gap-2">
                                        <span class="rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-red-100 text-red-900 border-red-200">
                                            critical
                                        </span>
                                        {#if issue.defect}
                                            <span class="text-xs font-medium text-gray-700">{issue.defect}</span>
                                        {/if}
                                        {#if issue.type}
                                            <span class="text-xs text-gray-600">{issue.type}</span>
                                        {/if}
                                    </div>
                                    <p class="mt-1.5 text-gray-900 leading-snug">{issue.message}</p>
                                    {#if issue.test_id || issue.phase != null || issue.step_index != null}
                                        <div class="mt-1.5 flex flex-wrap gap-x-3 text-xs text-gray-700/70">
                                            {#if issue.test_id}
                                                <span>Test <span class="font-mono">{issue.test_id}</span></span>
                                            {/if}
                                            {#if issue.phase}
                                                <span class="capitalize">{issue.phase}</span>
                                            {/if}
                                            {#if issue.step_index != null}
                                                <span>Step {issue.step_index}</span>
                                            {/if}
                                            {#if issue.selector}
                                                <span class="truncate max-w-full font-mono text-[11px]">{issue.selector}</span>
                                            {/if}
                                        </div>
                                    {/if}
                                </li>
                            {/each}
                        </ul>
                    </div>
                {/if}

                {#if issuesList.length > 0}
                    <div>
                        <h3 class="mb-3 text-sm font-medium text-gray-800">Issue list</h3>
                        <ul class="space-y-2">
                            {#each issuesList as item, i (`${i}-${item._bucket}-${item.message ?? ""}`)}
                                <li
                                    class="rounded-lg border border-l-4 border-gray-100 bg-slate-50/50 px-3 py-2.5 text-sm {issueBorderClass(
                                        item._bucket
                                    )}"
                                >
                                    <div class="flex flex-wrap items-center gap-2">
                                        <span
                                            class="rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide {severityPillClass(
                                                item._bucket
                                            )}"
                                        >
                                            {item._bucket}
                                        </span>
                                        {#if item.defect}
                                            <span class="text-xs font-medium text-gray-600">{item.defect}</span>
                                        {/if}
                                        {#if item.type}
                                            <span class="text-xs text-gray-500">{item.type}</span>
                                        {/if}
                                    </div>
                                    <p class="mt-1.5 text-gray-800 leading-snug">{item.message}</p>
                                    {#if item.test_id || item.phase != null || item.step_index != null}
                                        <div class="mt-1.5 flex flex-wrap gap-x-3 text-xs text-gray-500">
                                            {#if item.test_id}
                                                <span>Test <span class="font-mono">{item.test_id}</span></span>
                                            {/if}
                                            {#if item.phase}
                                                <span class="capitalize">{item.phase}</span>
                                            {/if}
                                            {#if item.step_index != null}
                                                <span>Step {item.step_index}</span>
                                            {/if}
                                            {#if item.selector}
                                                <span class="truncate max-w-full font-mono text-[11px]"
                                                    >{item.selector}</span
                                                >
                                            {/if}
                                        </div>
                                    {/if}
                                </li>
                            {/each}
                        </ul>
                    </div>
                {:else if scanResult && latest.status === "completed"}
                    <p class="text-sm text-gray-600">No issues reported for this run.</p>
                {/if}
            </section>
        {/if}
    </div>
</div>
