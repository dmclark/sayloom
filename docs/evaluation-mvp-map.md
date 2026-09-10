# Evaluation and Smart MVP map

- **Status:** Canonical implementation and evidence map
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Issue tracker:** [`dmclark/sayloom`](https://github.com/dmclark/sayloom/issues)
- **Last reconciled:** 2026-09-10

This map separates the Current product cleanup track from the Smart-correction track and names the
evidence required for each Smart milestone. Implementation evidence does not prove that a private
run happened, and protocol approval does not authorize implementation, corpus access, provider
calls, spending, or operation.

## Two independent evaluation tracks

| Track | Product contract | Machinery and evidence | Boundary |
| --- | --- | --- | --- |
| **Cleanup evaluation** | Original → Conservative source-preserving preparation → Prepared | Issues [#25](https://github.com/dmclark/sayloom/issues/25) through [#32](https://github.com/dmclark/sayloom/issues/32) implemented the separate cleanup benchmark/canary evaluation machinery. The approved protocol remains [`cleanup-evaluation-benchmark-v2.json`](cleanup-evaluation-benchmark-v2.json). | No live run or operational authorization follows from implementation. Cleanup results do not validate Smart correction. |
| **Smart evaluation** | Original + ephemeral context + explicitly enabled Private correction profile → Smart correction → reviewable repairs + Prepared | [`correction_benchmark.py`](../src/local_text/correction_benchmark.py) and [`test_correction_benchmark.py`](../tests/test_correction_benchmark.py) provide a generic, synthetically tested 2 × 2 × 2 scaffold. Issue [#14](https://github.com/dmclark/sayloom/issues/14) must bind it to the implemented Smart contract and complete acceptance. | Do not reuse the cleanup runner, corpus, protocol, or results. The product-bound freeze is blocked by [#10](https://github.com/dmclark/sayloom/issues/10) and [#12](https://github.com/dmclark/sayloom/issues/12). |

The cleanup protocol files are provenance-bearing records. In particular,
[`cleanup-evaluation-benchmark-v1.json`](cleanup-evaluation-benchmark-v1.json) remains byte-for-byte
unchanged historical evidence. Implementation-status statements embedded in older protocol or
design prose describe their recorded baseline; this map owns current cross-track status.

## Smart milestone sequence

| Order | Milestone | Completion evidence |
| ---: | --- | --- |
| 0 | **Current product** | Shipped Conservative source-preserving preparation produces Prepared from Original. The cleanup evaluation machinery is separate and does not change this product contract. |
| 1 | **Smart MVP candidate** | [#6](https://github.com/dmclark/sayloom/issues/6) completes Original/Prepared vocabulary migration; [#10](https://github.com/dmclark/sayloom/issues/10) implements Smart Prepared generation; [#11](https://github.com/dmclark/sayloom/issues/11) adds repair review; [#12](https://github.com/dmclark/sayloom/issues/12) adds the explicitly enabled Private correction profile; then [#14](https://github.com/dmclark/sayloom/issues/14) binds and accepts the real Smart benchmark contract. |
| 2 | **Evidence-backed Smart MVP** | [#15](https://github.com/dmclark/sayloom/issues/15) receives separate approval, runs against the private Smart corpus, and passes its frozen gates. A scaffold, synthetic test pass, or approved protocol is insufficient. |
| 3 | **Locally proven Smart product** | [#13](https://github.com/dmclark/sayloom/issues/13) and [#16](https://github.com/dmclark/sayloom/issues/16) complete the later memory-inclusive product scope and local self-pilot. Memory is optional and outside the MVP. |
| 4 | **Partner-demo ready** | [#17](https://github.com/dmclark/sayloom/issues/17) completes partner-demo readiness after local proof. |

Issue [#9](https://github.com/dmclark/sayloom/issues/9) is the coordinating Smart-correction
initiative. The dependency order above, rather than cleanup issue completion, determines Smart
milestone advancement.

## Reading older documents

- [`product-implementation-plan.md`](product-implementation-plan.md) remains the active capability
  plan; this map controls its Smart issue order, milestone names, and evidence gates.
- [`correction-benchmark-pipeline.md`](correction-benchmark-pipeline.md) documents the existing Smart
  scaffold, not an accepted product-bound benchmark or permission to run it.
- [`cleanup-evaluation-successor-protocol.md`](cleanup-evaluation-successor-protocol.md) and its JSON
  protocols govern cleanup only. They are not Smart evaluation inputs.
- [`roadmap.md`](roadmap.md) and
  [`research/first-correction-model-and-experiment-matrix.md`](research/first-correction-model-and-experiment-matrix.md)
  are retained historical context, not current milestone or execution authority.
