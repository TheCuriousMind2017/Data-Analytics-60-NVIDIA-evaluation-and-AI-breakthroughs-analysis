# Diagnostic Analysis — Findings

**Pillar 1 · Structural-break detection.** This section dates the regime changes in
NVIDIA's market price and fundamentals and reports where they fall relative to the three
AI milestones — **AlexNet (2012Q3)**, the **Transformer (2017Q3)**, and **ChatGPT (2022Q4)**.

> **Framing — temporal alignment, not causation.** The tests below identify *when* each
> series changes regime and *how confidently* the break is dated; they say nothing about
> *why*. A break that coincides with a milestone is *consistent with* that milestone but
> is **not** evidence that it caused the shift. Crypto cycles (2017–18, 2020–21), COVID
> (2020), and the broad macro/semiconductor cycle move in the same windows and are kept
> visible as confounder bands. Every result is read as alignment only.

## Method

Two complementary tests are run on each series, both at 15% symmetric trimming with
wild-bootstrap *p*-values (Rademacher, residuals resampled under the relevant null) and
bootstrapped break-date confidence intervals.

- **Bai–Perron** — global dynamic-programming search for an unknown number of breaks at
  unknown dates; break count selected by **BIC** and cross-checked with sequential
  sup-*F* tests. Reports *how many* regime changes and *where*.
- **Quandt–Andrews** — sup-Wald test for a *single* unknown break (max Chow *F* over all
  admissible dates). Reports the *dominant* inflection; complements Bai–Perron where the
  structure has several breaks.

Series transforms (the confirmed specification):

| Series | Transform | Model | A "break" means |
|---|---|---|---|
| Price | `log(price)`, level | trend (`[1, t]`) | a change in the compound-growth slope (re-rating) |
| Revenue | YoY log growth `log Xt − log Xt-4` | mean (`[1]`) | a shift in the average growth rate |
| Net income | YoY log growth (2010Q2 loss dropped) | mean (`[1]`) | a shift in the average growth rate |

YoY differencing deseasonalises the fundamentals (like-quarter vs like-quarter) and
stationarises them, so the test dates growth-regime shifts rather than seasonal swings.
Price has no quarterly seasonality, so the level is tested.

## Results

### Bai–Perron (BIC-selected)

| Series | model | n | breaks | break quarters | 90% CIs |
|---|---|---|---|---|---|
| log(price) | trend | 65 | **3** | 2015Q1, 2018Q4, 2022Q2 | 2014Q4–2015Q3; 2018Q4; 2022Q2 |
| YoY log revenue growth | mean | 60 | **1** | **2023Q2** | 2022Q3–2023Q2 |
| YoY log net-income growth | mean | 58 | **1** | **2023Q2** | 2021Q4–2024Q1 |

Sequential sup-*F* agrees with BIC in every case: for revenue and net income the second
break is rejected (bootstrap *p* ≈ 0.2 and ≈ 0.6); for price the breaks are supported
through the third (the fourth is borderline and worsens BIC).

### Quandt–Andrews (sup-Wald, single break)

| Series | n | break | supF | boot *p* | aveF | expF |
|---|---|---|---|---|---|---|
| log(price) | 65 | 2015Q4 | 40.6 | <0.01 | 20.3 | 17.8 |
| YoY log revenue growth | 60 | **2023Q2** | 52.2 | <0.01 | 14.9 | 22.4 |
| YoY log net-income growth | 58 | **2023Q2** | 15.8 | ≈0.01 | 3.8 | 4.6 |

### Break dates vs AI milestones

| Series | Bai–Perron | Quandt–Andrews | nearest milestone | note |
|---|---|---|---|---|
| log(price) | 2015Q1, 2018Q4, 2022Q2 | 2015Q4 | — | first break precedes all milestones; 2018Q4 & 2022Q2 on confounders |
| YoY log revenue growth | 2023Q2 | 2023Q2 | ChatGPT 2022Q4 | single break, CI straddles gen-AI onset |
| YoY log net-income growth | 2023Q2 | 2023Q2 | ChatGPT 2022Q4 | single break, wide CI, coincides with revenue |

Figures: `figures/12_break_price.png`, `figures/13_break_revenue.png`,
`figures/14_break_netincome.png`. Machine-readable tables:
`findings/bai_perron_results.csv`, `findings/quandt_andrews_results.csv`.

## Reading

**Fundamentals break once, at the generative-AI onset.** NVIDIA's YoY revenue growth and
YoY net-income growth each contain exactly **one** structural break, both dated **2023Q2**,
and the result is **double-corroborated** — Bai–Perron's BIC-selected search and the
Quandt–Andrews sup-Wald, two methodologically different procedures, agree to the quarter.
Both confidence intervals straddle the **ChatGPT marker (2022Q4)**. This is the cleanest,
most robust result in the analysis.

**Price re-rates earlier, and not on the AI milestones.** Price shows **three** trend
breaks (2015Q1, 2018Q4, 2022Q2; dominant single break 2015Q4). The re-rating *begins in
2015* — before the Transformer and generative-AI markers — and the later two breaks fall
on the **late-2018 crypto/market correction** and the **2022 rate-hike sell-off** rather
than on any milestone (ChatGPT is two quarters after the 2022Q2 break). The drivers of
the 2015 break are not identified by this test and are **not** attributed here.

**Net effect.** NVIDIA's generative-AI alignment is a **fundamentals** phenomenon
(revenue, net income), not a price one: the fundamentals change regime once, at gen-AI,
while the price trajectory re-rates earlier and is partly entangled with sector/macro
confounders.

## Limitations

- **Single firm; no control or counterfactual.** These tests date NVIDIA's own breaks;
  they are not a causal design. (A peer divergence comparison against AMD/Intel exists as
  separate, supplementary *descriptive* evidence and is not a causal control.)
- **Modest sample.** ~58–65 quarterly observations give limited power and fairly wide
  break-date confidence intervals, widest for net income.
- **Window edge.** Quarterly fundamentals end 2025Q4 while price runs to 2026Q1.
- **No segment corroboration.** The annual Data Center segment-revenue source could not
  be verified and is treated as unreliable; no segment-based narrative is drawn.
