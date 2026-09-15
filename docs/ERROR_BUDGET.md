# Error-budget burn monitoring

xbow-perso can evaluate reliability deterioration using the 5-minute and 1-hour rolling worker-outcome windows.

## Reliability target

The default target success rate is 99%, leaving a 1% error budget.

`XBOW_SLO_TARGET_SUCCESS_RATE` can change the target between 90% inclusive and 100% exclusive.

Burn rate is calculated as:

`observed failure rate / allowed failure rate`

A burn rate of 1 consumes error budget at exactly the planned rate. A burn rate above 1 consumes it faster.

## Multi-window policy

The initial policy uses both windows together to reduce noisy alerts.

- critical fast burn: 5-minute burn >= 14.4 and 1-hour burn >= 6;
- degraded elevated burn: 5-minute burn >= 6 and 1-hour burn >= 3.

At least 20 short-window outcomes and 100 one-hour outcomes are required before either signal is emitted. This prevents an idle installation from paging because of a single failed job.

## Safety

The calculation is read-only and consumes aggregate failure rates and counts only. It does not inspect targets, payloads, credentials, scanner output, or finding contents.

A burn alert is an incident signal. It does not authorize retries, duplicated work, scope expansion, or bypassing execution controls.
