# Evaluation and automatic-correction prototype map

- **Status:** Canonical evaluation map
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Prototype specification:**
  [`automatic-correction-prototype-spec.md`](automatic-correction-prototype-spec.md)
- **Issue tracker:** [`dmclark/sayloom`](https://github.com/dmclark/sayloom/issues)
- **Last reconciled:** 2026-09-16

This map separates Current-product Cleanup evaluation from the
automatic-correction prototype's Smart evaluation. The focused specification
defines done. Implementation evidence does not prove that a private run
happened, and protocol approval does not authorize corpus access, provider
calls, spending, stable-state operation, deployment, or production hosting.

## Two independent evaluation tracks

| Track | Product contract | Machinery and evidence | Boundary |
| --- | --- | --- | --- |
| **Cleanup evaluation** | Original → Conservative source-preserving preparation → Prepared | Issues [#25](https://github.com/dmclark/sayloom/issues/25) through [#32](https://github.com/dmclark/sayloom/issues/32) implemented the separate cleanup benchmark/canary evaluation machinery. The approved protocol remains [`cleanup-evaluation-benchmark-v2.json`](cleanup-evaluation-benchmark-v2.json). | No live run or operational authorization follows from implementation. Cleanup results do not validate Smart correction. |
| **Smart evaluation** | Original + legitimately available ephemeral evidence → automatic selection among Correction methods → reviewable repairs + Conservative preparation → Prepared | [`automatic_strategy_evaluation.py`](../src/local_text/automatic_strategy_evaluation.py), its [harness contract](automatic-strategy-evaluation-harness.md), and the issue [#46](https://github.com/dmclark/sayloom/issues/46) graph provide the provider-neutral pipeline. The latest audit found zero eligible cases, so evidence accumulation remains the first evidence gate. | Experimental methods stay outside runtime. Do not reuse Cleanup evidence or weaken the held-out minimum and strata requirements. The earlier fixed 2 × 2 × 2 Smart scaffold is historical only. |

The cleanup protocol files are provenance-bearing records. In particular,
[`cleanup-evaluation-benchmark-v1.json`](cleanup-evaluation-benchmark-v1.json) remains byte-for-byte
unchanged historical evidence. Implementation-status statements embedded in older protocol or
design prose describe their recorded baseline; this map owns current cross-track status.

## Automatic-correction prototype sequence

| Order | Milestone | Completion evidence |
| ---: | --- | --- |
| 0 | **Current product** | Shipped Conservative source-preserving preparation produces Prepared from Original. The cleanup evaluation machinery is separate and does not change this product contract. |
| 1 | **Protocol and harness frozen** | Issues [#47](https://github.com/dmclark/sayloom/issues/47)–[#50](https://github.com/dmclark/sayloom/issues/50) froze the decisions, and [#56](https://github.com/dmclark/sayloom/issues/56) built the provider-neutral harness. This is implementation evidence, not efficacy evidence. |
| 2 | **Evidence ready** | [#60](https://github.com/dmclark/sayloom/issues/60) accumulates eligible evidence and freezes a content-free audit proving 60/20/20 grouped partitions, all required strata, observed-use weights, and at least 200 held-out cases. Issue [#57](https://github.com/dmclark/sayloom/issues/57) established the current insufficient-evidence baseline. |
| 3 | **Finalists frozen** | Experimental candidate adapters are compared on development and validation evidence outside runtime; no more than three complete strategies plus planned ablations are preregistered before held-out evidence opens. |
| 4 | **Winner selected** | [#51](https://github.com/dmclark/sayloom/issues/51) produces the approved private held-out evidence, and [#52](https://github.com/dmclark/sayloom/issues/52) selects a passing strategy or records that none qualifies. |
| 5 | **Automatic Smart prototype verified** | Only the winner is integrated inside Smart, then automatic routing, repair review, uncertainty, stale-state, fail-open, privacy, CART, and Outgoing contracts receive an explicit pass/stop result. |
| 6 | **Limited pilot complete** | A separately authorized, bounded shareable pilot completes without becoming production hosting or supporting a broad efficacy claim. |

Issue [#46](https://github.com/dmclark/sayloom/issues/46) is the automatic-correction
prototype initiative. Issue [#9](https://github.com/dmclark/sayloom/issues/9)
retains the broader production Smart and personalization history. Its fixed-arm
issues [#14](https://github.com/dmclark/sayloom/issues/14) and
[#15](https://github.com/dmclark/sayloom/issues/15) are superseded by the
automatic-strategy path rather than parallel acceptance gates.

## Reading older documents

- [`product-implementation-plan.md`](product-implementation-plan.md) remains the
  broader capability plan; the focused prototype specification controls the
  automatic-strategy definition of done and evidence gates.
- [`correction-benchmark-pipeline.md`](correction-benchmark-pipeline.md) documents the existing Smart
  fixed-arm scaffold, not the prototype acceptance benchmark or permission to
  run it.
- [`cleanup-evaluation-successor-protocol.md`](cleanup-evaluation-successor-protocol.md) and its JSON
  protocols govern cleanup only. They are not Smart evaluation inputs.
- [`roadmap.md`](roadmap.md) and
  [`research/first-correction-model-and-experiment-matrix.md`](research/first-correction-model-and-experiment-matrix.md)
  are retained historical context, not current milestone or execution authority.
