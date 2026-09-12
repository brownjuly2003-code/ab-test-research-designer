# ASOS public-pilot fixtures

These files are deterministic aggregate-only subsets of the **ASOS Digital
Experiments Dataset** by C. H. Bryan Liu, Angelo Cardoso, Paul Couturier, and
Emma J. McCoy (2021), DOI `10.17605/OSF.IO/64JSB`.

- Source: <https://osf.io/64jsb/>
- Original Parquet: <https://osf.io/download/62t7f/>
- License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- Original SHA-256:
  `bdf88b27185d3f7e65912cbb421129a32ae347c2fb0d9442fe54d74266551524`

The source has 78 real online experiments. These three subsets were selected
without looking at outcomes: from the 54 complete experiments with one
treatment and four metrics, sort by the terminal Metric 1 total sample size and
take the nearest 25th, 50th, and 75th percentile ranks (14, 28, and 41).

| Experiment | Rows | SHA-256 |
| --- | ---: | --- |
| `d53f0e` | 184 | `b190ce2e295e72e79bc77289af38d7e3d8c95373350262a5711fce5c3dc9a78b` |
| `26bd38` | 272 | `f71c7a8b617ff000ce61f6fd6692a48f7632eee065dc8321bdf62ac0a54452b3` |
| `834947` | 340 | `8d345cc311258bb8e6e413e99f7c80ce3c0110219f42c254c9b5cf0c4f3d9953` |

Each subset retains the complete sorted time series for one experiment, one
treatment, and all four aggregate metrics. They are modified extracts of the
CC BY 4.0 source and retain the same license.

These files are `public_benchmark` evidence with `partner_approved=false`.
They do not represent design-partner adoption and do not change Gate 3.

## Deterministic ABX benchmark artifacts

`benchmark-context.json` records the explicit retrospective harness assumptions
needed by the ABX protocol schema but unavailable from the published extract.
Its fixed timestamps are reproducibility anchors, not partner timing evidence.
The context does not reconstruct ASOS's original protocol or hidden metric
semantics.

Each file under `bundles/` contains one protocol, run, source, terminal query,
four metric documents, and four aggregate-only mean-difference estimates. No
decision, finding, raw Parquet row, local path, or secret is included.

| Experiment | Archive SHA-256 | Trialmark bundle ID |
| --- | --- | --- |
| `d53f0e` | `5fb64dd809aba8e701314874679d7d56794a411e1b177ab3265f2de5b54ce1f0` | `sha256:60fee3fae970b607fec89bec8d6e8fc423d55a42f6d3f02b679436c281b694b3` |
| `26bd38` | `76a9e2411ec8254d77b0ec7200b3bde2adec0cd061481949a029be92d7395536` | `sha256:de3b8372fc60bfb8049455d738febde068a062386de8f9253d32177c0025c942` |
| `834947` | `4b747b3f81c2862e8c374089c1b627d5bde0bc7639084d6a6f7c0d230e3148ec` | `sha256:0f6654308d5e89ceb89a780498c79079049b5c087fcb444e444d9a722266602a` |

The archive bytes bind the runtime environment: `runner.dependency_lock_digest`
is `sha256(app/backend/requirements.txt)`. A deliberate runtime-lock change
therefore re-packs these bundles and rotates the digests above — the table was
last rotated on 2026-09-07, when the estimate p-value moved to `erfc` and was
quantised to 12 significant digits so the identity stops depending on the host
libm (see `_benchmark_p_value` in `app/evidence/public_pilot_abx.py`).

The Archive SHA-256 column identifies the committed file, not every faithful
re-pack of it: per ADR 0004 the bundle ID is the identity, because the ZIP byte
stream also carries the deflate output of whatever zlib the interpreter links
against. CPython 3.14 compresses these same members to a different size than
3.13 does, so `test_packs_deterministic_offline_asos_public_benchmark` compares
a fresh pack member by member and pins the bundle ID, and pins the archive
digest against the committed file alone.

All three bundles verify offline with schema, integrity, reference, lineage,
and privacy verdicts passing. `statistical_validity` remains `not_asserted`,
and Gate 3 remains `PIVOT` until real partner evidence exists.
